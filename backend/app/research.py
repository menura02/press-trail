"""Research findings and notifications share the collection transaction."""
import re

from sqlalchemy import or_, select

from .analysis import analysis_lock
from .db import Session, now
from .evolution_models import ClaimPair, Finding, Notification, VersionDiff, Watch
from .models import Cluster, Link, Member, Version
from .version_diff import METHOD, PARAGRAPH, SENTENCE, compact, compare_versions, expressions

ANALYZER = "turkish-sentence-rules-v1"
MANUAL = "manual-selection-v1"
PAIR_RULE = "exact-normalized-quote-v1"
CORRECTION = re.compile(
    r"^\s*(?:[“\"«]\s*)?(?:düzeltme|güncelleme)\s*[:—–-]|"
    r"\b(?:haberin|haberimizin|bu haberin|metnin)\s+(?:bir\s+)?önceki\s+sürüm(?:ü|ünde|ünde de)?\b|"
    r"\b(?:haberi|haberimizi|bu haberi)\s+(?:güncelledik|düzelttik)\b",
    re.IGNORECASE,
)
MAX_FINDINGS_PER_KIND = 120


def diff_for(db, before, after):
    if before.id > after.id:
        before, after = after, before
    row = db.scalar(select(VersionDiff).where(VersionDiff.before_id == before.id,
                                             VersionDiff.after_id == after.id, VersionDiff.method == METHOD))
    if row is None:
        row = VersionDiff(article_id=before.article_id, before_id=before.id, after_id=after.id, method=METHOD)
        db.add(row)
        db.flush()
    return row


def complete_diff(db, row):
    if row.completed_at is None:
        before, after = db.get(Version, row.before_id), db.get(Version, row.after_id)
        links = {before.id: [], after.id: []}
        for version_id, url in db.execute(select(Link.version_id, Link.url).where(Link.version_id.in_(links))):
            links[version_id].append(url)
        row.result = compare_versions(before, after, links[before.id], links[after.id])
        row.completed_at = now()
    return row


def spans(value):
    offset = 0
    for boundary in [*PARAGRAPH.finditer(value), None]:
        end = boundary.start() if boundary else len(value)
        cursor = offset
        paragraph = value[offset:end]
        for cut in [*SENTENCE.finditer(paragraph), None]:
            stop = offset + cut.start() if cut else end
            excerpt = value[cursor:stop]
            start = cursor + len(excerpt) - len(excerpt.lstrip())
            final = cursor + len(excerpt.rstrip())
            if start < final:
                yield start, final
            if cut:
                cursor = offset + cut.end()
        if boundary:
            offset = boundary.end()


def save_finding(db, version, kind, field, start, end, method):
    existing = db.scalar(select(Finding).where(
        Finding.version_id == version.id, Finding.kind == kind, Finding.field == field,
        Finding.start == start, Finding.end == end))
    if existing:
        return existing, False
    value = getattr(version, field)
    quote = value[start:end]
    item = Finding(version_id=version.id, kind=kind, field=field, start=start, end=end,
                   quote=quote, context=value[max(0, start - 180):min(len(value), end + 180)],
                   signals=expressions(quote), method=method)
    db.add(item)
    db.flush()
    return item, True


def pair_for(db, cluster_id, first_id, second_id, method):
    left, right = sorted((first_id, second_id))
    row = db.scalar(select(ClaimPair).where(ClaimPair.cluster_id == cluster_id,
                                           ClaimPair.left_id == left, ClaimPair.right_id == right))
    if row is None:
        row = ClaimPair(cluster_id=cluster_id, left_id=left, right_id=right, method=method)
        db.add(row)
        db.flush()
    return row


def suggest_pairs(db, version, cluster_id, claims):
    if not cluster_id or not claims:
        return
    others = db.scalars(select(Finding).join(Version, Version.id == Finding.version_id)
                        .join(Member, Member.article_id == Version.article_id)
                        .where(Member.cluster_id == cluster_id, Version.article_id != version.article_id,
                               Finding.kind == "claim", Finding.status != "rejected")
                        .order_by(Finding.id.desc()).limit(300)).all()
    indexed = {}
    for item in others:
        indexed.setdefault(compact(item.quote), item)
    for claim in claims:
        if claim.status != "rejected" and (match := indexed.get(compact(claim.quote))):
            pair_for(db, cluster_id, claim.id, match.id, PAIR_RULE)


def notify(db, kind, version, cluster_id, key, *, diff=None, finding=None):
    watched = or_(
        (Watch.target_kind == "article") & (Watch.target_id == version.article_id),
        (Watch.target_kind == "cluster") & (Watch.target_id == cluster_id),
    )
    if kind == "group_join":
        watched = (Watch.target_kind == "cluster") & (Watch.target_id == cluster_id)
    if not db.scalar(select(Watch.id).where(watched).limit(1)):
        return
    if db.scalar(select(Notification.id).where(Notification.event_key == key)):
        return
    cluster = db.get(Cluster, cluster_id) if cluster_id else None
    db.add(Notification(event_key=key, kind=kind, article_id=version.article_id, cluster_id=cluster_id,
                        version_id=version.id, diff_id=diff.id if diff else None,
                        finding_id=finding.id if finding else None, title=version.title,
                        cluster_title=cluster.title if cluster else None))


def membership_event(db, version, old_group, new_group):
    if new_group and old_group != new_group:
        notify(db, "group_join", version, new_group, f"group:{new_group}:article:{version.article_id}")


def analyze_version(db, version, previous=None, *, live=False):
    if version.evolution_method == ANALYZER:
        return
    if previous is None:
        previous = db.scalar(select(Version).where(Version.article_id == version.article_id, Version.id < version.id)
                             .order_by(Version.id.desc()).limit(1))
    member = db.get(Member, version.article_id)
    cluster_id = member.cluster_id if member else None
    if previous is not None:
        diff = complete_diff(db, diff_for(db, previous, version))
        if live and diff.result["content_changed"]:
            notify(db, "version_changed", version, cluster_id, f"version:{version.id}", diff=diff)
    counters = {"claim": 0, "correction": 0}
    claims = []
    seen_corrections = set()
    for field in ("title", "body" if version.body else "summary"):
        value = getattr(version, field)
        for start, end in spans(value):
            if end - start > 2400:
                continue
            quote = value[start:end]
            signals = expressions(quote)
            kinds = []
            if any(signals.values()):
                kinds.append("claim")
            normalized = compact(quote)
            if CORRECTION.search(quote) and normalized not in seen_corrections:
                kinds.append("correction")
                seen_corrections.add(normalized)
            for kind in kinds:
                if counters[kind] >= MAX_FINDINGS_PER_KIND:
                    continue
                counters[kind] += 1
                item, created = save_finding(db, version, kind, field, start, end, ANALYZER)
                if kind == "claim":
                    claims.append(item)
                elif live and created and (previous is None or not any(
                    normalized in compact(text) for text in (previous.title, previous.summary, previous.body)
                )):
                    notify(db, "correction", version, cluster_id, f"correction:{item.id}", finding=item)
    suggest_pairs(db, version, cluster_id, claims)
    version.evolution_method = ANALYZER


def process_analysis():
    """One unit per tick, with pending explicit requests ahead of history."""
    with Session.begin() as db:
        analysis_lock(db)
        pending = db.scalar(select(VersionDiff).where(VersionDiff.method == METHOD, VersionDiff.completed_at.is_(None))
                            .order_by(VersionDiff.id).limit(1))
        if pending:
            complete_diff(db, pending)
            return True
        version = db.scalar(select(Version).where(or_(Version.evolution_method.is_(None),
                                                      Version.evolution_method != ANALYZER))
                            .order_by(Version.id).limit(1))
        if version:
            analyze_version(db, version)
            return True
        return False

