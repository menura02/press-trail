from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Barrier

import pytest
from sqlalchemy import func, select

from app.collectors import Entry
from app.db import Session, now
from app.demo import seed
from app.models import Article, Member, Run, Source, Version
from app.network import FetchError, Response
from app.queue import MAX_ATTEMPTS, claim, enqueue, fail, owned, schedule
from app.worker import process, store

FIRST = "https://gazete.example.org/rss"
SECOND = "https://atom.example.org/feed.xml"
FIRST_ARTICLE = "https://gazete.example.org/haber?konu=baraj&sayi=1"
SECOND_ARTICLE = "https://atom.example.org/bulten/olcum"


class FixtureClient:
    def __init__(self, fixtures):
        self.fixtures = fixtures
        self.changed = False
        self.blocked = False
        self.calls = []

    def get(self, url, headers=None):
        self.calls.append((url, headers))
        if url in {FIRST, SECOND}:
            file = "news.rss" if url == FIRST else "news.atom"
            return Response(url, 200, {"etag": '"v1"'}, (self.fixtures / file).read_bytes())
        if self.blocked:
            raise FetchError("robots")
        body = (self.fixtures / "news.html").read_bytes()
        if self.changed:
            body = body.replace("salı sabahı".encode(), "salı öğleden sonra".encode())
        return Response(url, 200, {"content-type": "text/html"}, body)


def add(api, url, name, full_text=True):
    response = api.post("/api/sources", json={"name": name, "url": url, "full_text": full_text})
    assert response.status_code == 201, response.text
    return response.json()


def collect(api, source, client):
    response = api.post(f"/api/sources/{source['id']}/runs")
    assert response.status_code == 202, response.text
    run = response.json()
    job = claim()
    assert job.id == run["id"]
    process(job, client)
    return next(r for r in api.get("/api/runs").json() if r["id"] == job.id)


def test_end_to_end(api, fixtures):
    client = FixtureClient(fixtures)
    a = add(api, FIRST, "Gazete")
    b = add(api, SECOND, "Atom")
    assert collect(api, a, client)["status"] == "partial"  # One broken item.
    assert collect(api, b, client)["status"] == "success"
    groups = api.get("/api/clusters").json()["items"]
    assert len(groups) == 1 and groups[0]["count"] == 2
    group_id = groups[0]["id"]
    detail = api.get(f"/api/clusters/{group_id}").json()
    first, second = detail["articles"]
    assert (first["url"], second["url"]) == (FIRST_ARTICLE, SECOND_ARTICLE)
    assert first["first_seen"] != first["version"]["published"]
    assert any(link["target_ids"] == [first["id"]] for link in detail["links"])
    result = api.get("/api/compare", params={"left": first["id"], "right": second["id"]}).json()
    assert result["method"] == "sha256-v1" and result["segments"]
    assert collect(api, a, client)["versions"] == 0
    assert collect(api, b, client)["versions"] == 0

    endpoint = f"/api/articles/{second['id']}"
    assert api.put(endpoint + "/membership", json={"decision": "excluded"}).status_code == 200
    client.changed = True
    assert collect(api, b, client)["versions"] == 1
    edited = api.get(endpoint).json()
    assert len(edited["versions"]) == 2
    assert edited["membership"]["decision"] == "excluded"
    assert api.get("/api/articles").json()[0]["id"] == second["id"]
    assert len(api.get(f"/api/clusters/{group_id}").json()["articles"]) == 1
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Article)) == 2
        assert db.scalar(select(func.count()).select_from(Version)) == 3

    client.changed = False
    assert collect(api, b, client)["versions"] == 1  # A → B → A is a new observation.
    assert api.put(endpoint + "/membership", json={"decision": "moved", "cluster_id": group_id}).status_code == 200
    assert api.put(endpoint + "/membership", json={"decision": "confirmed"}).json()["decision"] == "confirmed"
    assert api.get("/api/clusters", params={"source_id": b["id"], "start": "2025-05-13",
                                           "end": "2025-05-13"}).json()["items"][0]["count"] == 2


def test_falls_back_to_summary(api, fixtures):
    client = FixtureClient(fixtures)
    client.blocked = True
    source = add(api, SECOND, "Atom")
    run = collect(api, source, client)
    assert (run["status"], run["error"]) == ("partial", "robots:1")
    group = api.get("/api/clusters").json()["items"][0]
    article = api.get(f"/api/clusters/{group['id']}").json()["articles"][0]
    assert article["version"]["scope"] == "feed" and article["version"]["summary"]


def test_conditional_feed_and_schedule(api, fixtures):
    client = FixtureClient(fixtures)
    source = add(api, SECOND, "Atom", full_text=False)
    schedule()
    run = api.get("/api/runs").json()[0]
    job = claim()
    assert job.id == run["id"]
    process(job, client)

    class Unchanged:
        def get(self, url, headers):
            assert url == SECOND and headers == {"If-None-Match": '"v1"'}
            return Response(url, 304, {}, b"")

    assert collect(api, source, Unchanged())["versions"] == 0


def test_feed_address_edit_preserves_articles_and_scopes_guids(api, fixtures):
    source = add(api, SECOND, "Atom", full_text=False)
    assert collect(api, source, FixtureClient(fixtures))["versions"] == 1
    new_url = "https://atom.example.org/updated.xml"
    changed = api.put(f"/api/sources/{source['id']}", json={"name": "Atom", "url": new_url})
    assert changed.status_code == 200

    class Replacement:
        def get(self, url, headers):
            assert url == new_url and headers == {}
            body = (fixtures / "news.atom").read_bytes().replace(b'href="olcum"', b'href="diger"')
            return Response(url, 200, {}, body)

    assert collect(api, source, Replacement())["versions"] == 1
    with Session() as db:
        articles = db.scalars(select(Article).order_by(Article.id)).all()
        assert [article.feed_url for article in articles] == [SECOND, new_url]
        assert [article.url for article in articles] == [SECOND_ARTICLE, "https://atom.example.org/bulten/diger"]


def test_group_rejects_similarity_chain(database):
    a = "baraj gölet doluluk su yağış ölçüm pompa tahliye taşkın hidroloji akarsu havza"
    c = "tramvay istasyon ulaşım sefer ücret ray durak yolcu tren aktarma vagon kalkış"
    with Session.begin() as db:
        sources = [Source(name=str(i), url=f"https://s{i}.example.com/rss") for i in range(3)]
        db.add_all(sources)
        db.flush()
        for index, (source, body) in enumerate(zip(sources, [a, a + " " + c, c], strict=True)):
            store(db, source, Entry(f"https://s{index}.example.com/a", None, "", "", None, None), body)
        members = db.scalars(select(Member).order_by(Member.article_id)).all()
        assert members[0].cluster_id == members[1].cluster_id
        assert members[1].cluster_id != members[2].cluster_id
        # C would pass with B in isolation.
        members[0].cluster_id = None
        members[0].decision = "excluded"
        store(db, sources[2], Entry("https://s2.example.com/a", None, "", "", None,
                                    "2025-01-01T00:00:00Z"), c)
        assert members[1].cluster_id == members[2].cluster_id


def test_language_window_and_short_text(database):
    with Session.begin() as db:
        source = Source(name="A", url="https://a.example.com/rss")
        db.add(source)
        db.flush()
        original = Entry("https://a.example.com/a", None, "Başlık", "Çok kısa", None, None)
        for i in range(2):
            store(db, source, replace(original, url=original.url + str(i)))
        long_text = "İzmir yağış Konak alt geçit trafik pompa ulaşım yol araç kapanış."
        store(db, source, replace(original, url=original.url + "new", published_raw="2025-05-15T12:00:00Z"), long_text)
        store(db, source, replace(original, url=original.url + "old", published_raw="2025-04-01T12:00:00Z"), long_text)
        assert len(set(db.scalars(select(Member.cluster_id)).all())) == 4


def test_queue_recovery_and_fencing(api):
    source = add(api, FIRST, "Gazete")
    endpoint = f"/api/sources/{source['id']}/runs"
    run_id = api.post(endpoint).json()["id"]
    assert api.post(endpoint).json()["id"] == run_id
    first = claim()
    assert first.id == run_id and claim() is None
    with Session.begin() as db:
        db.get(Run, run_id).lease_until = now() - timedelta(seconds=1)
    recovered = claim()
    assert recovered.id == run_id and recovered.token != first.token
    with Session.begin() as db:
        assert owned(db, first) is None
        assert owned(db, recovered).attempts == 2
    fail(recovered, "timeout")
    assert claim() is None
    with Session.begin() as db:
        db.get(Run, run_id).available_at = now() - timedelta(seconds=1)
    final = claim()
    with Session.begin() as db:
        run = owned(db, final)
        assert run.attempts == MAX_ATTEMPTS
        run.lease_until = now() - timedelta(seconds=1)
    assert claim() is None
    run = api.get("/api/runs").json()[0]
    assert (run["status"], run["error"]) == ("failed", "lease_expired")


def test_postgres_concurrent_claims(database):
    if database.dialect.name != "postgresql":
        pytest.skip("Gerçek satır kilidi için TEST_DATABASE_URL gereklidir.")
    with Session.begin() as db:
        source = Source(name="A", url="https://a.example.com/rss")
        db.add(source)
        db.flush()
        run_id = enqueue(db, source).id
    barrier = Barrier(2)

    def take():
        barrier.wait(timeout=5)
        return claim()

    with ThreadPoolExecutor(2) as threads:
        jobs = list(threads.map(lambda _: take(), range(2)))
    assert [job.id for job in jobs if job is not None] == [run_id]


def test_api_validation_and_editing(api):
    assert api.post("/api/sources", json={"name": "A", "url": "file:///tmp/a"}).status_code == 422
    assert api.post("/api/sources", json={"name": "A", "url": FIRST, "interval_minutes": 4}).status_code == 422
    source = add(api, FIRST, "A")
    assert api.post("/api/sources", json={"name": "A", "url": FIRST}).status_code == 409
    url = f"/api/sources/{source['id']}"
    paused = api.put(url, json={"name": "B", "url": FIRST, "active": False}).json()
    assert paused["name"] == "B" and not paused["active"]
    assert api.post(url + "/runs").status_code == 409
    assert api.post(url + "/runs", headers={"Origin": "https://evil.example"}).status_code == 403
    assert api.get("/api/articles/999").status_code == 404
    assert api.get("/api/compare?left=1&right=1").status_code == 422
    assert api.get("/api/clusters?start=2025-02-01&end=2025-01-01").status_code == 422


def test_demo_is_idempotent(api):
    seed()
    seed()
    assert len(api.get("/api/sources").json()) == 3
    groups = api.get("/api/clusters").json()["items"]
    assert sorted(g["count"] for g in groups) == [1, 2]
    assert all(g["demo"] for g in groups)
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Version)) == 4

