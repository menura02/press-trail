import hashlib
import os
import re
import unicodedata
from datetime import timedelta

from sklearn.feature_extraction.text import TfidfVectorizer
from sqlalchemy import func, select, text
from sqlalchemy.orm import aliased

from .models import Article, Cluster, Member, Source, Version

THRESHOLD = 0.48
MIN_WORDS = 8
WINDOW_HOURS = max(1, int(os.getenv("MATCH_WINDOW_HOURS", "72")))
METHOD = f"tfidf-v1@{THRESHOLD}/{WINDOW_HOURS}h"
WORDS = re.compile(r"[^\W_]+", re.UNICODE)


def normalize(value):
    value = unicodedata.normalize("NFC", value).translate(str.maketrans("Iİ", "ıi"))
    return " ".join(WORDS.findall(value.lower()))


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def document(version):
    return normalize(f"{version.title} {version.body or version.summary}")


def matrices(versions):
    docs = [document(v) for v in versions]
    vectorizer = TfidfVectorizer(tokenizer=str.split, token_pattern=None, lowercase=False,
                                 ngram_range=(1, 2), sublinear_tf=True, max_features=60000)
    vectors = vectorizer.fit_transform([doc or "__empty__" for doc in docs])
    return docs, vectors


def score(a, b, da, db, va, vb):
    if a.digest == b.digest and a.scope == b.scope and len(da.split()) >= MIN_WORDS:
        return 1.0, "sha256-v1"
    if min(len(da.split()), len(db.split())) < MIN_WORDS:
        return None, "short"
    return min(1.0, float(va.multiply(vb).sum())), METHOD


def latest():
    newer = aliased(Version)
    return Version.id == select(func.max(newer.id)).where(
        newer.article_id == Article.id).correlate(Article).scalar_subquery()


def analysis_lock(db):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(582951)"))


def assign(db, article, version, source):
    member = db.get(Member, article.id)
    if member and member.decision != "automatic":
        return
    anchor = version.published or article.first_seen
    window = timedelta(hours=WINDOW_HOURS)
    rows = db.execute(
        select(Article, Version, Member)
        .join(Version, Version.article_id == Article.id)
        .join(Source, Source.id == Article.source_id)
        .join(Member, Member.article_id == Article.id)
        .where(latest(), Article.id != article.id, Source.language == source.language,
               Source.demo == source.demo, Member.cluster_id.is_not(None),
               func.coalesce(Version.published, Article.first_seen).between(anchor - window, anchor + window))
        .order_by(Article.id.desc()).limit(300)
    ).all()
    candidates = {}
    if rows:
        docs, vectors = matrices([version, *(v for _, v, _ in rows)])
        for index, (_, other, item) in enumerate(rows, 1):
            result = score(version, other, docs[0], docs[index], vectors[0], vectors[index])
            candidates.setdefault(item.cluster_id, []).append(result)
    # A group can be joined only if all current members were eligible and passed.
    counts = dict(db.execute(select(Member.cluster_id, func.count()).where(
        Member.cluster_id.in_(candidates), Member.article_id != article.id
    ).group_by(Member.cluster_id)).all()) if candidates else {}
    eligible = []
    for cluster_id, results in candidates.items():
        if counts[cluster_id] == len(results) and all(
            value is not None and value >= THRESHOLD for value, _ in results
        ):
            weakest = min(results, key=lambda pair: pair[0])
            eligible.append((weakest[0], -cluster_id, weakest[1]))
    if eligible:
        value, negative_id, method = max(eligible)
        cluster_id = -negative_id
    elif member and member.cluster_id and not db.scalar(select(Member.article_id).where(
        Member.cluster_id == member.cluster_id, Member.article_id != article.id).limit(1)
    ):
        cluster_id, value, method = member.cluster_id, None, METHOD
        db.get(Cluster, cluster_id).title = version.title or "(Başlıksız)"
    else:
        group = Cluster(title=version.title or "(Başlıksız)")
        db.add(group)
        db.flush()
        cluster_id, value, method = group.id, None, METHOD
    if not member:
        member = Member(article_id=article.id, decision="automatic")
        db.add(member)
    member.cluster_id, member.score, member.method = cluster_id, value, method

