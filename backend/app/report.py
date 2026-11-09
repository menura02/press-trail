"""Self-contained research reports with escaped, bounded evidence excerpts."""
from html import escape
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from .analysis import latest
from .db import database, now
from .evolution_api import require
from .evolution_models import Annotation, Finding, VersionDiff
from .models import Article, Cluster, Link, Member, Source, Version
from .network import FetchError, normalize_url

ISTANBUL = ZoneInfo("Europe/Istanbul")
router = APIRouter(prefix="/api")
FIELDS = {"title": "Başlık", "summary": "Özet", "body": "Metin"}
KINDS = {"article": "Haber", "version": "Sürüm", "diff": "Fark", "finding": "Aday"}
STATUSES = {"pending": "İnceleme bekliyor", "confirmed": "Onaylandı", "rejected": "Reddedildi",
            "open": "Açık", "reviewed": "İncelendi", "resolved": "Tamamlandı"}


class ReportInput(BaseModel):
    finding_ids: list[int] = Field(default_factory=list, max_length=20)
    diff_ids: list[int] = Field(default_factory=list, max_length=20)
    recent_diffs: bool = True
    include_notes: bool = True


def safe(value):
    return escape(str(value), quote=True)


def short(value, size=240):
    return safe(value[:size] + ("…" if len(value) > size else ""))


def stamp(value):
    return value.astimezone(ISTANBUL).isoformat(timespec="seconds") if value else "Bilinmiyor"


def time_info(version):
    reported = stamp(version.published) if version.published else (
        f"{safe(version.published_raw or 'Bilinmiyor')} · yayın zamanı doğrulanamadı"
    )
    return f"Bildirilen yayın: {reported} · Toplama: {stamp(version.collected_at)}"


def url_link(raw):
    try:
        url = normalize_url(raw)
    except FetchError:
        return short(raw)
    return f'<a href="{safe(url)}" rel="noreferrer noopener">{short(url)}</a>'


def section(title, blocks, empty="Seçilen kapsamda kayıt yok."):
    return f"<section><h2>{title}</h2>{''.join(blocks) or f'<p>{empty}</p>'}</section>"


def render(db, cluster, payload):
    rows = db.execute(select(Article, Source, Version).join(Member, Member.article_id == Article.id)
                      .join(Source, Source.id == Article.source_id).join(Version, Version.article_id == Article.id)
                      .where(Member.cluster_id == cluster.id, latest()).order_by(Article.id).limit(301)).all()
    if len(rows) > 300:
        raise HTTPException(422, "Bu rapor en çok 300 üye haber destekler.")
    article_ids = {article.id for article, _, _ in rows}
    latest_ids = {v.id for _, _, v in rows}
    findings = db.execute(select(Finding, Version).join(Version, Version.id == Finding.version_id)
                          .where(Finding.id.in_(payload.finding_ids)).order_by(Finding.id)).all()
    diffs = db.scalars(select(VersionDiff).where(VersionDiff.id.in_(payload.diff_ids))
                       .order_by(VersionDiff.id.desc())).all()
    if (len(findings) != len(set(payload.finding_ids)) or len(diffs) != len(set(payload.diff_ids))
            or any(v.article_id not in article_ids for _, v in findings)
            or any(d.article_id not in article_ids or d.completed_at is None for d in diffs)):
        raise HTTPException(422, "Bulgular tamamlanmış ve seçilen grubun güncel üye haberlerine ait olmalı.")
    if payload.recent_diffs:
        recent = db.scalars(select(VersionDiff).where(
            VersionDiff.article_id.in_(article_ids), VersionDiff.completed_at.is_not(None)
        ).order_by(VersionDiff.id.desc()).limit(10)).all()
        known = {d.id for d in diffs}
        diffs.extend(d for d in recent if d.id not in known)

    source_blocks = []
    for article, source, version in rows:
        label = " · Kurgusal örnek" if source.demo else ""
        source_blocks.append(f"<article><h3>{short(version.title, 220)}</h3>"
                             f"<p>{safe(source.name)}{label} · Haber #{article.id} · Sürüm #{version.id}</p>"
                             f"<p>{time_info(version)}</p><p>{url_link(article.url)}</p></article>")
    selected_versions = latest_ids | {v.id for _, v in findings} | {
        identity for d in diffs for identity in (d.before_id, d.after_id)
    }
    link_blocks = [f"<li>Sürüm #{link.version_id} · {short(link.text, 100)} · {url_link(link.url)}</li>"
                   for link in db.scalars(select(Link).where(Link.version_id.in_(selected_versions))
                                          .order_by(Link.id).limit(200))]
    quote_blocks = [f"<article><h3>Aday #{item.id} · {'Düzeltme / güncelleme' if item.kind == 'correction' else 'İddia'}</h3>"
                    f"<p>Haber #{v.article_id} · Sürüm #{v.id} · {time_info(v)}</p>"
                    f"<blockquote>{short(item.quote)}</blockquote><p>Yöntem: {safe(item.method)} · "
                    f"{STATUSES[item.status]} · Konum: {FIELDS[item.field]} {item.start}–{item.end}</p></article>"
                    for item, v in findings]
    diff_blocks = []
    for diff in diffs:
        before, after = db.get(Version, diff.before_id), db.get(Version, diff.after_id)
        flags = []
        if diff.result["extractor_changed"] or diff.result["scope_changed"]:
            flags.append("<p>Çıkarıcı veya kapsam farklı. Değişikliğin bir bölümü toplama yönteminden kaynaklanabilir.</p>")
        for field, detail in diff.result["fields"].items():
            flags.append(f"<h4>{FIELDS[field]}</h4>")
            if detail["format_only"]:
                flags.append("<p>Boşluk / biçim farkı.</p>")
            if detail.get("formatted"):
                flags.append(f"<p>{detail['formatted']} eşleşen paragrafta boşluk / biçim farkı var.</p>")
            sizes = [min(120, len(getattr(version, field)) // 2) if field != "title" else 120
                     for version in (before, after)]
            for p in detail["paragraphs"][:3]:
                label = {"added": "Eklendi", "removed": "Kaldırıldı", "changed": "Değişti", "moved": "Taşındı"}
                flags.append(f"<p><strong>{label[p['kind']]}</strong> · Önce: {short(p['before'], sizes[0])}"
                             f" · Sonra: {short(p['after'], sizes[1])}</p>")
            signals = diff.result["signals"].get(field, {})
            for key, label in (("numbers", "Sayı"), ("dates", "Tarih"), ("quotes", "Alıntı")):
                for direction, status in (("added", "Eklendi"), ("removed", "Kaldırıldı")):
                    items = signals.get(key, {}).get(direction, [])
                    if items:
                        flags.append(f"<p>{label} · {status} · " + " / ".join(short(item, 90) for item in items[:5]) + "</p>")
            if len(detail["paragraphs"]) > 3 or detail["truncated"]:
                flags.append("<p>Bu raporda farkın bir bölümü gösteriliyor.</p>")
        for key, label in (("added", "Eklenen bağlantı"), ("removed", "Kaldırılan bağlantı")):
            flags.extend(f"<p>{label} · {url_link(url)}</p>" for url in diff.result["links"][key][:10])
        diff_blocks.append(f"<article><h3>Fark #{diff.id} · Haber #{diff.article_id}</h3>"
                           f"<p>Sürüm #{before.id} · {time_info(before)}</p>"
                           f"<p>Sürüm #{after.id} · {time_info(after)}</p>"
                           f"<p>Bu iki kontrol arasında gözlendi. Yöntem: {safe(diff.method)}</p>"
                           + ("".join(flags) or "<p>Metin ve bağlantı farkı yok.</p>") + "</article>")

    note_blocks = []
    if payload.include_notes:
        targets = {"article": article_ids, "version": selected_versions,
                   "diff": {d.id for d in diffs}, "finding": {f.id for f, _ in findings}}
        rules = [(Annotation.target_kind == kind) & Annotation.target_id.in_(ids)
                 for kind, ids in targets.items() if ids]
        if rules:
            for note in db.scalars(select(Annotation).where(or_(*rules)).order_by(Annotation.id).limit(100)):
                tags = " · ".join(safe(tag) for tag in note.tags)
                note_blocks.append(f"<article><h3>{KINDS[note.target_kind]} #{note.target_id} · Not #{note.id}</h3>"
                                   f"<p>{STATUSES[note.status]} · {stamp(note.updated_at)} · {tags}</p>"
                                   f"<p class='note'>{safe(note.text)}</p></article>")

    title = safe(cluster.title)
    source_scope = f"Grup #{cluster.id} · {len(rows)} güncel üye · İstanbul saati"
    filters = (f"Seçili aday: {len(findings)} · Seçili fark: {len(set(payload.diff_ids))} · "
               f"Son farklar: {'dahil' if payload.recent_diffs else 'hariç'} · "
               f"Araştırmacı notları: {'dahil' if payload.include_notes else 'hariç'}")
    return f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>İz Sürücüsü · {title}</title><style>
body{{font:16px/1.55 system-ui,sans-serif;color:#363636;background:#fff;margin:2rem auto;padding:0 1rem;max-width:55rem;overflow-wrap:anywhere}}
h1{{line-height:1.1}} section{{border-top:1px solid #ccc;margin-top:1.5rem}} article{{margin-block:1.2rem}}
a{{color:#a20d2b}} blockquote{{border-left:4px solid #ff83a5;margin:1rem 0;padding:.5rem 1rem;background:#fff0f4}}
.note{{white-space:pre-wrap}} li{{margin-bottom:.5rem}}
</style></head><body><header><p>İZ SÜRÜCÜSÜ / ARAŞTIRMA RAPORU</p><h1>{title}</h1>
<p>{source_scope}</p><p>Oluşturma: {stamp(now())}</p><p>Kapsam: {filters}</p></header>
{section("Kaynaklar ve zamanlar", source_blocks)}
{section("Metindeki bağlantılar", ["<ul>" + "".join(link_blocks) + "</ul>"] if link_blocks else [])}
{section("Seçilen kısa alıntılar", quote_blocks)}
{section("Sürüm farkları", diff_blocks)}
{section("Araştırmacı notları", note_blocks)}
<section><h2>Belirsizlikler ve sınırlar</h2><p>Yayıncı tarihleri bildirime dayanır. Toplama zamanı, değişikliğin
gerçekleştiği anı göstermez. Eksik kapsam, biçim ve çıkarıcı farkları gözlemi etkileyebilir. Adaylar ve eşleştirmeler
araştırma kayıtlarıdır. Farklı sayılar farklı zamanları veya kapsamları anlatabilir.</p><p>Rapor kısa alıntılar,
alan başına en çok üç paragraf farkı, en çok 200 bağlantı ve 100 not içerir. Kaynak adresleri açıldığında
internet bağlantısı gerekebilir.</p></section></body></html>"""


@router.post("/clusters/{cluster_id}/report", response_class=HTMLResponse)
def group_report(cluster_id: int, payload: ReportInput, db=Depends(database)):
    cluster = require(db, Cluster, cluster_id)
    return HTMLResponse(render(db, cluster, payload), headers={
        "Content-Disposition": f'attachment; filename="iz-surucusu-grup-{cluster_id}.html"',
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'",
        "X-Content-Type-Options": "nosniff",
    })

