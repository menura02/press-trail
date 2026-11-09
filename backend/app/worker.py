import json
import logging
import time
from collections import Counter

from sqlalchemy import select

from .analysis import analysis_lock, assign, digest
from .collectors import extract, parse_date, parse_feed
from .db import Session
from .models import Article, Link, Member, Source, Version
from .network import Client, FetchError
from .queue import claim, fail, finish, owned, renew, schedule
from .research import analyze_version, membership_event, process_analysis

log = logging.getLogger(__name__)


def store(db, source, entry, body="", links=()):
    article = db.scalar(select(Article).where(Article.source_id == source.id, Article.url == entry.url))
    if article is None and entry.feed_id:
        matches = db.scalars(select(Article).where(Article.source_id == source.id,
                                                    Article.feed_id == entry.feed_id,
                                                    Article.feed_url == source.url).limit(2)).all()
        if len(matches) == 1:
            article = matches[0]
    if article is None:
        article = Article(source_id=source.id, url=entry.url, feed_id=entry.feed_id, feed_url=source.url)
        db.add(article)
        db.flush()
    elif not article.feed_id:
        article.feed_id = entry.feed_id
        if entry.feed_id:
            article.feed_url = source.url
    scope = "full" if body else "feed"
    extractor = "readability-v1" if body else "feedparser-v1"
    content = digest(body or entry.summary or entry.title)
    fingerprint = digest(json.dumps([entry.title, entry.summary, body, entry.published_raw,
                                     entry.updated_raw, scope, extractor, links], sort_keys=True))
    previous = db.scalar(select(Version).where(Version.article_id == article.id)
                         .order_by(Version.id.desc()).limit(1))
    if previous and previous.fingerprint == fingerprint:
        return 0
    published, published_state = parse_date(entry.published_raw)
    updated, updated_state = parse_date(entry.updated_raw)
    version = Version(article_id=article.id, title=entry.title, summary=entry.summary, body=body,
                      digest=content, fingerprint=fingerprint, published=published, updated=updated,
                      published_raw=entry.published_raw, updated_raw=entry.updated_raw,
                      published_state=published_state, updated_state=updated_state,
                      scope=scope, extractor=extractor)
    db.add(version)
    db.flush()
    db.add_all(Link(version_id=version.id, **link) for link in links)
    member = db.get(Member, article.id)
    old_group = member.cluster_id if member else None
    assign(db, article, version, source)
    member = db.get(Member, article.id)
    if member:
        membership_event(db, version, old_group, member.cluster_id)
    analyze_version(db, version, previous, live=True)
    return 1


def process(job, client):
    with Session() as db:
        source = db.get(Source, job.source_id)
        db.expunge(source)
    if not source.active or source.demo:
        with Session.begin() as db:
            run = owned(db, job)
            if run:
                finish(run, "cancelled")
        return
    headers = {}
    if not source.full_text:
        if source.etag:
            headers["If-None-Match"] = source.etag
        if source.modified:
            headers["If-Modified-Since"] = source.modified
    try:
        response = client.get(source.url, headers)
        if response.status == 304:
            entries, skipped = [], 0
        elif response.status == 200:
            entries, skipped = parse_feed(response)
        else:
            raise FetchError("http_retry" if response.status >= 500 or response.status == 429 else "http")
        gathered = []
        failures = Counter()
        feed_ids = Counter(entry.feed_id for entry in entries if entry.feed_id)
        for entry in entries:
            if entry.feed_id and feed_ids[entry.feed_id] > 1:
                entry.feed_id = None
            body, links = "", []
            if source.full_text:
                if not renew(job, source.revision):
                    return
                try:
                    body, links = extract(client.get(entry.url))
                except FetchError as exc:
                    failures[exc.kind] += 1
            gathered.append((entry, body, links))
    except FetchError as exc:
        fail(job, exc.kind)
        return
    with Session.begin() as db:
        current = db.get(Source, source.id, with_for_update=True)
        run = owned(db, job)
        if not run:
            return
        if not current.active or current.revision != source.revision:
            finish(run, "cancelled")
            return
        analysis_lock(db)
        run.seen, run.skipped = len(gathered), skipped
        run.versions = sum(store(db, current, entry, body, links) for entry, body, links in gathered)
        if response.status == 200:
            current.etag = response.headers.get("etag")
            current.modified = response.headers.get("last-modified")
        error = ",".join(f"{kind}:{count}" for kind, count in sorted(failures.items())) or None
        finish(run, "partial" if skipped or failures else "success", error)


def main():
    client = Client()
    while True:
        analyzed = False
        try:
            analyzed = process_analysis()
        except Exception:
            log.error("Sürüm analizi tamamlanamadı.")
        try:
            schedule()
            job = claim()
            if job:
                try:
                    process(job, client)
                except Exception:
                    log.error("İş tamamlanamadı. İş kimliği %s", job.id)
                    fail(job, "internal")
                continue
            if analyzed:
                continue
        except Exception:
            log.error("İş kuyruğuna erişilemedi.")
        time.sleep(3)


if __name__ == "__main__":
    main()

