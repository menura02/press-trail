from dataclasses import replace
from types import SimpleNamespace

from sqlalchemy import func, select

from app.collectors import Entry
from app.db import Session
from app.evolution_models import Finding, Notification, VersionDiff
from app.models import Article, Member, Source, Version
from app.research import analyze_version, process_analysis
from app.version_diff import compare_versions, text_diff
from app.worker import store
from test_workflow import SECOND, FixtureClient, add, collect


def captured(title="Başlık", body="", summary="", extractor="readability-v1", scope="full"):
    return SimpleNamespace(title=title, body=body, summary=summary, extractor=extractor, scope=scope)


def test_version_diff_preserves_turkish_and_detects_edits():
    before = captured(title="İzmir’de ölçüm", body=(
        "İzmir’de 13 Mayıs 2025 tarihinde 17 kişi sayıldı.\n\n"
        "Yetkili “ölçüm sürüyor” dedi.\n\nÖnceki paragraf."))
    after = captured(title="İzmir’de ikinci ölçüm", body=(
        "İzmir’de 14 Mayıs 2025 tarihinde 24 kişi sayıldı.\n\n"
        "Yetkili “ölçüm tamamlandı” dedi.\n\nYeni açıklama.\n\nEk paragraf."))
    diff = compare_versions(before, after, ["https://example.com/eski"], ["https://example.com/yeni"])
    assert diff["content_changed"]
    assert diff["fields"]["title"]["paragraphs"][0]["words"][0]["after"] == "ikinci"
    paragraphs = diff["fields"]["body"]["paragraphs"]
    assert paragraphs[0]["sentences"]["removed"] == ["İzmir’de 13 Mayıs 2025 tarihinde 17 kişi sayıldı."]
    assert any(p["kind"] == "added" for p in paragraphs)
    signals = diff["signals"]["body"]
    assert signals["numbers"] == {"removed": ["17 kişi"], "added": ["24 kişi"]}
    assert signals["dates"] == {"removed": ["13 Mayıs 2025"], "added": ["14 Mayıs 2025"]}
    assert signals["quotes"] == {"removed": ["“ölçüm sürüyor”"], "added": ["“ölçüm tamamlandı”"]}
    assert diff["links"] == {"removed": ["https://example.com/eski"], "added": ["https://example.com/yeni"]}
    removed = text_diff("İlk.\n\nKaldırılan bölüm.", "İlk.")
    assert removed["paragraphs"][0]["kind"] == "removed"


def test_unchanged_format_moved_and_extractor_are_separate():
    old = captured(body="Çığ bilgisi.\n\nİkinci paragraf.\n\nÜçüncü paragraf.")
    assert not compare_versions(old, old, [], [])["content_changed"]
    assert not compare_versions(old, old, [], [])["fields"]
    formatted = captured(body="Çığ   bilgisi.\n\nİkinci paragraf.\nÜçüncü paragraf.")
    diff = compare_versions(old, formatted, [], [])
    assert diff["fields"]["body"]["format_only"] and not diff["content_changed"]
    moved = text_diff(old.body, "İkinci paragraf.\n\nÜçüncü paragraf.\n\nÇığ bilgisi.")
    assert [p["kind"] for p in moved["paragraphs"]] == ["moved"]
    assert moved["paragraphs"][0]["before_index"] == 1 and moved["paragraphs"][0]["after_index"] == 3
    diff = compare_versions(old, captured(body=old.body, extractor="readability-v2", scope="feed"), [], [])
    assert diff["extractor_changed"] and diff["scope_changed"] and not diff["content_changed"]


def add_local(db, title, body, slug="ilk", source=None, links=()):
    if source is None:
        source = Source(name="Deneme " + slug, url=f"https://{slug}.example.invalid/rss")
        db.add(source)
        db.flush()
    entry = Entry(f"https://{slug}.example.invalid/haber", slug, title, "", "2025-05-13T10:00:00+03:00", None)
    store(db, source, entry, body, links)
    article = db.scalar(select(Article).where(Article.source_id == source.id, Article.url == entry.url))
    version = db.scalar(select(Version).where(Version.article_id == article.id).order_by(Version.id.desc()))
    return article.id, version.id, db.get(Member, article.id).cluster_id, source


class ChangedClient(FixtureClient):
    def get(self, url, headers=None):
        response = super().get(url, headers)
        if not self.changed:
            return response
        if url == SECOND:
            return replace(response, body=response.body.replace("ölçümü açıklandı".encode(), "ölçümü yenilendi".encode()))
        if response.status == 200:
            body = response.body.replace("yüzde kırk sekize".encode(), "%49’a".encode())
            body = body.replace(b"</article>", "<p>Güncelleme: Ölçüm 13 Mayıs 2025 tarihinde yinelendi.</p></article>".encode())
            return replace(response, body=body)
        return response


def test_worker_to_report_workflow(api, fixtures):
    source = add(api, SECOND, "Yayıncı <img src=x>", full_text=True)
    client = ChangedClient(fixtures)
    assert collect(api, source, client)["versions"] == 1
    group_id = api.get("/api/clusters").json()["items"][0]["id"]
    article_id = api.get(f"/api/clusters/{group_id}").json()["articles"][0]["id"]
    original = api.get(f"/api/articles/{article_id}").json()["versions"][0]
    assert api.put(f"/api/watch/article/{article_id}", json={"watching": True}).json()["watching"]
    assert api.put(f"/api/watch/cluster/{group_id}", json={"watching": True}).json()["watching"]

    client.changed = True
    assert collect(api, source, client)["versions"] == 1
    assert collect(api, source, client)["versions"] == 0
    current = api.get(f"/api/articles/{article_id}").json()["versions"][0]
    request = {"before_id": original["id"], "after_id": current["id"]}
    result = api.post(f"/api/articles/{article_id}/diffs", json=request).json()
    assert not result["pending"]
    diff_id = result["id"]
    diff = api.get(f"/api/diffs/{diff_id}").json()
    assert diff["before"]["id"] == original["id"]
    assert diff["after"]["collected_at"] == current["collected_at"]
    assert diff["result"]["fields"]["title"] and diff["result"]["fields"]["body"]
    assert "%49" in diff["result"]["signals"]["body"]["numbers"]["added"]

    findings = api.get(f"/api/versions/{current['id']}/findings").json()["items"]
    correction = next(f for f in findings if f["kind"] == "correction")
    assert correction["status"] == "pending"
    assert correction["quote"].startswith("Güncelleme:")
    assert api.put(f"/api/findings/{correction['id']}/review", json={"status": "confirmed"}).status_code == 200
    body = current["body"]
    quote = body.split(". ")[0] + "."
    payload = {"field": "body", "start": 0, "end": len(quote), "quote": quote}
    assert api.post(f"/api/versions/{current['id']}/findings", json={**payload, "quote": "Yanlış"}).status_code == 422
    chosen = api.post(f"/api/versions/{current['id']}/findings", json=payload)
    assert chosen.status_code == 201, chosen.text
    claim = chosen.json()
    assert claim["version"]["id"] == current["id"] and claim["quote"] == body[:len(quote)]
    assert api.post(f"/api/versions/{current['id']}/findings", json=payload).json()["id"] == claim["id"]

    note_url = f"/api/annotations/finding/{claim['id']}"
    saved = api.post(note_url, json={"text": "İncele <script>alert(1)</script>", "tags": [" ölçüm ", "ölçüm"]})
    assert saved.status_code == 201 and saved.json()["tags"] == ["ölçüm"]
    note_id = saved.json()["id"]
    changed = api.put(f"/api/annotations/{note_id}", json={"text": "İncelendi <script>alert(1)</script>",
                                                           "tags": ["ölçüm"], "status": "reviewed"}).json()
    assert changed["status"] == "reviewed"
    assert changed["updated_at"] >= changed["created_at"]

    inbox = api.get("/api/notifications?unread=true").json()["items"]
    assert {n["kind"] for n in inbox} == {"version_changed", "correction"}
    change = next(n for n in inbox if n["kind"] == "version_changed")
    assert change["diff_id"] == diff_id
    assert api.put(f"/api/notifications/{change['id']}", json={"read": True}).json()["read_at"]
    assert len(api.get("/api/notifications?unread=true").json()["items"]) == 1
    assert api.put(f"/api/notifications/{change['id']}", json={"read": False}).json()["read_at"] is None

    html = api.post(f"/api/clusters/{group_id}/report", json={
        "finding_ids": [claim["id"], correction["id"]], "diff_ids": [diff_id], "recent_diffs": False})
    assert html.status_code == 200, html.text
    assert "attachment" in html.headers["content-disposition"]
    assert "default-src 'none'" in html.headers["content-security-policy"]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html.text and "<script>" not in html.text
    assert "Yayıncı &lt;img src=x&gt;" in html.text and "<img" not in html.text
    assert quote in html.text and current["body"] not in html.text
    assert "Sürüm farkları" in html.text and "Belirsizlikler" in html.text
    assert api.delete(f"/api/annotations/{note_id}").status_code == 204
    assert api.get(note_url).json()["items"] == []
    assert api.put(f"/api/watch/article/{article_id}", json={"watching": False}).json() == {"watching": False}
    assert api.get("/api/watch?limit=1").json()["items"][0]["target_kind"] == "cluster"


def test_rules_scope_and_manual_decisions_survive_backfill(api):
    with Session.begin() as db:
        a, va, group, _ = add_local(db, "Ardıç ölçümü",
            "Belediye ekipleri bölgede ortak ölçüm çalışması başlattı ve sonuçları yayımladı. "
            "13 Mayıs 2025 tarihinde 15 kişi katıldı. Yazılım güncelleme aracı kuruldu.")
        b, vb, _, _ = add_local(db, "Ardıç ikinci ölçüm",
            "Belediye ekipleri bölgede ortak ölçüm çalışması başlattı ve sonuçları yayımladı. "
            "14 Mayıs 2025 tarihinde 25 kişi katıldı. Düzeltme: Önceki sayı düzeltilmiştir.", "ikinci")
        db.get(Member, b).cluster_id = group
    a_findings = api.get(f"/api/versions/{va}/findings").json()["items"]
    b_findings = api.get(f"/api/versions/{vb}/findings").json()["items"]
    assert all(item["kind"] != "correction" for item in a_findings)
    assert any(item["kind"] == "correction" for item in b_findings)
    left = next(item for item in a_findings if "15 kişi" in item["quote"])
    right = next(item for item in b_findings if "25 kişi" in item["quote"])
    assert api.get(f"/api/clusters/{group}/claim-comparisons").json()["items"] == []

    pair_url = f"/api/clusters/{group}/claim-comparisons"
    pair = api.post(pair_url, json={"left_id": left["id"], "right_id": right["id"]}).json()
    assert pair["status"] == "pending" and pair["left"]["signals"]["dates"] != pair["right"]["signals"]["dates"]
    assert "contradiction" not in pair
    assert api.post(pair_url, json={"right_id": left["id"], "left_id": right["id"]}).json()["id"] == pair["id"]
    assert api.put(f"/api/claim-comparisons/{pair['id']}/review", json={"status": "rejected"}).status_code == 200
    assert api.put(f"/api/findings/{left['id']}/review", json={"status": "rejected"}).status_code == 200
    with Session.begin() as db:
        version = db.get(Version, va)
        version.evolution_method = None
        analyze_version(db, version)
        assert db.get(Finding, left["id"]).status == "rejected"
    assert api.get(pair_url).json()["items"][0]["status"] == "rejected"
    assert api.put(f"/api/articles/{b}/membership", json={"decision": "excluded"}).status_code == 200
    assert not api.get(pair_url).json()["items"][0]["current_group"]


def test_same_sentence_suggests_pending_pair(api):
    content = "Belediye ekipleri yeni ölçümü yerel halkla birlikte tamamladı. 15 Mayıs 2025 tarihinde 19 kişi katıldı."
    with Session.begin() as db:
        _, _, group, _ = add_local(db, "Ölçüm tamamlandı", content)
        _, _, second_group, _ = add_local(db, "Yeni ölçüm tamamlandı", content, "ikinci")
        assert group == second_group
    pairs = api.get(f"/api/clusters/{group}/claim-comparisons").json()["items"]
    assert len(pairs) == 1 and pairs[0]["status"] == "pending"
    assert pairs[0]["method"] == "exact-normalized-quote-v1"


def test_group_join_dedup_and_historical_context(api):
    with Session.begin() as db:
        _, _, group, _ = add_local(db, "Ardıç ölçümü",
            "Belediye ekipleri bugün su seviyesi için ölçüm yaptı ve güncel sonuçları yerel halka bildirdi.")
        b, vb, old_group, _ = add_local(db, "İzmir ulaşım",
            "İzmir merkezde metro trenleri bakım çalışması sırasında durdu ve yolcular aktarma otobüslerine bindi.", "metro")
        assert group != old_group
    assert api.put(f"/api/watch/cluster/{group}", json={"watching": True}).status_code == 200
    path = f"/api/articles/{b}/membership"
    for decision in [{"decision": "moved", "cluster_id": group}, {"decision": "excluded"},
                     {"decision": "moved", "cluster_id": group}, {"decision": "excluded"}]:
        assert api.put(path, json=decision).status_code == 200
    records = api.get("/api/notifications").json()["items"]
    assert len(records) == 1
    assert records[0]["kind"] == "group_join" and records[0]["cluster_id"] == group
    assert records[0]["version_id"] == vb and records[0]["cluster_title"] == "Ardıç ölçümü"


def test_nonadjacent_requested_diff_runs_in_worker(api):
    with Session.begin() as db:
        article, first, _, source = add_local(db, "İlk başlık", "Çalışma henüz başlamadı.")
        _, _, _, _ = add_local(db, "İkinci başlık", "Çalışma 14 Mayıs 2025 tarihinde başladı.", source=source)
        _, third, _, _ = add_local(db, "Üçüncü başlık", "Çalışma 15 Mayıs 2025 tarihinde tamamlandı.", source=source)
    url = f"/api/articles/{article}/diffs"
    response = api.post(url, json={"before_id": third, "after_id": first}).json()
    assert response["pending"]
    assert api.get(f"/api/diffs/{response['id']}").json()["result"] is None
    assert api.post(url, json={"before_id": first, "after_id": third}).json()["id"] == response["id"]
    assert process_analysis()
    assert api.get(f"/api/diffs/{response['id']}").json()["result"]["content_changed"]
    assert not process_analysis()
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(VersionDiff)) == 3
        assert db.scalar(select(func.count()).select_from(Notification)) == 0


def test_report_selection_scope_and_safe_urls(api):
    malicious = {"url": "javascript:alert(42)", "text": "<iframe>", "context": "", "kind": "link"}
    with Session.begin() as db:
        article, version, group, _ = add_local(db, "<svg onload=alert(1)>", "15 kişi katıldı.", links=[malicious])
        foreign, foreign_version, _, _ = add_local(db, "Başka haber", "100 metre yol yapıldı.", "yol")
        assert article != foreign
    foreign_finding = api.get(f"/api/versions/{foreign_version}/findings").json()["items"][0]["id"]
    assert api.post(f"/api/clusters/{group}/report", json={"finding_ids": [foreign_finding]}).status_code == 422
    response = api.post(f"/api/clusters/{group}/report", json={})
    assert response.status_code == 200
    assert "&lt;svg" in response.text and "&lt;iframe&gt;" in response.text
    assert 'href="javascript:' not in response.text and "<svg" not in response.text
    assert "15 kişi katıldı." not in response.text
    assert api.post(f"/api/articles/{article}/diffs", json={"before_id": version, "after_id": foreign_version}).status_code == 422

