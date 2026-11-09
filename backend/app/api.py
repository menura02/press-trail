from datetime import UTC, date, datetime, time, timedelta
from difflib import SequenceMatcher
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .analysis import METHOD, THRESHOLD, analysis_lock, latest, matrices, normalize, score
from .db import database, now
from .evolution_api import router as research_router
from .models import Article, Cluster, Link, Member, Run, Source, Version
from .network import FetchError, normalize_url
from .queue import enqueue
from .research import membership_event
from .report import router as report_router

app = FastAPI(title="Haber Kaynağı İz Sürücüsü")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
app.include_router(research_router)
app.include_router(report_router)
ISTANBUL = ZoneInfo("Europe/Istanbul")


@app.middleware("http")
async def local_mutations(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if (request.headers.get("sec-fetch-site") == "cross-site"
                or (origin is not None and origin != f"http://{request.headers.get('host')}")):
            return JSONResponse({"detail": "Yalnızca aynı kökenden değişiklik yapılabilir."}, status_code=403)
    return await call_next(request)


class SourceInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(max_length=1600)
    language: Literal["tr"] = "tr"
    interval_minutes: int = Field(default=60, ge=5, le=1440)
    active: bool = True
    full_text: bool = False

    @field_validator("url")
    @classmethod
    def validate_url(cls, value):
        try:
            return normalize_url(value)
        except FetchError:
            raise ValueError("Geçerli bir HTTP veya HTTPS adresi girin.") from None


class DecisionInput(BaseModel):
    decision: Literal["confirmed", "moved", "excluded"]
    cluster_id: int | None = Field(default=None, gt=0)


def fields(obj, *names):
    return {name: getattr(obj, name) for name in names}


def source_view(source):
    return fields(source, "id", "name", "url", "language", "active", "full_text", "interval_minutes",
                  "next_check", "demo")


def run_view(run):
    return fields(run, "id", "source_id", "status", "created_at", "started_at", "finished_at",
                  "attempts", "seen", "versions", "skipped", "error")


def version_view(version, include_body=False):
    result = fields(version, "id", "title", "summary", "published", "updated", "published_raw",
                    "updated_raw", "published_state", "updated_state", "collected_at", "scope", "extractor")
    if include_body:
        result["body"] = version.body
    return result


def article_view(article, source, version, member):
    return {**fields(article, "id", "url", "first_seen"), "source": source_view(source),
            "version": version_view(version),
            "membership": fields(member, "cluster_id", "decision", "method", "score") if member else None}


def article_query():
    return (select(Article, Source, Version, Member)
            .join(Source, Source.id == Article.source_id)
            .join(Version, Version.article_id == Article.id)
            .outerjoin(Member, Member.article_id == Article.id)
            .where(latest()))


def get_article(db, article_id):
    result = db.execute(article_query().where(Article.id == article_id)).first()
    if result is None:
        raise HTTPException(404, "Haber bulunamadı.")
    return result


@app.get("/api/health")
def health(db=Depends(database)):
    db.scalar(select(1))
    return {"status": "ok"}


@app.get("/api/sources")
def sources(db=Depends(database)):
    return [source_view(s) for s in db.scalars(select(Source).order_by(Source.id))]


def commit_source(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Bu RSS adresi zaten kayıtlı.") from None


@app.post("/api/sources", status_code=201)
def add_source(payload: SourceInput, db=Depends(database)):
    source = Source(**payload.model_dump())
    db.add(source)
    commit_source(db)
    return source_view(source)


@app.put("/api/sources/{source_id}")
def edit_source(source_id: int, payload: SourceInput, db=Depends(database)):
    source = db.get(Source, source_id, with_for_update=True)
    if source is None:
        raise HTTPException(404, "Kaynak bulunamadı.")
    if source.demo:
        raise HTTPException(409, "Örnek kaynaklar düzenlemeye kapalıdır.")
    changed = source.url != payload.url or source.full_text != payload.full_text
    if changed:
        source.etag = source.modified = None
    if changed or source.active != payload.active:
        source.revision += 1
    if changed or source.active != payload.active or source.interval_minutes != payload.interval_minutes:
        source.next_check = now() + timedelta(minutes=payload.interval_minutes)
    for key, value in payload.model_dump().items():
        setattr(source, key, value)
    commit_source(db)
    return source_view(source)


@app.post("/api/sources/{source_id}/runs", status_code=202)
def trigger(source_id: int, db=Depends(database)):
    source = db.get(Source, source_id, with_for_update=True)
    if source is None:
        raise HTTPException(404, "Kaynak bulunamadı.")
    if not source.active or source.demo:
        raise HTTPException(409, "Yalnızca aktif gerçek kaynaklar kontrol edilebilir.")
    run = enqueue(db, source)
    source.next_check = now() + timedelta(minutes=source.interval_minutes)
    db.commit()
    return run_view(run)


@app.get("/api/runs")
def runs(db=Depends(database)):
    return [run_view(r) for r in db.scalars(select(Run).order_by(Run.id.desc()).limit(50))]


@app.get("/api/clusters")
def clusters(q: str = Query(default="", max_length=150), source_id: int | None = None,
             start: date | None = None, end: date | None = None,
             offset: int = Query(default=0, ge=0), db=Depends(database)):
    if start and end and start > end:
        raise HTTPException(422, "Başlangıç tarihi bitişten sonra olamaz.")
    matching = (select(Member.cluster_id).join(Article, Article.id == Member.article_id)
                .join(Version, Version.article_id == Article.id)
                .join(Cluster, Cluster.id == Member.cluster_id).where(latest()))
    if q:
        matching = matching.where(Version.title.icontains(q, autoescape=True) |
                                  Cluster.title.icontains(q, autoescape=True))
    if source_id:
        matching = matching.where(Article.source_id == source_id)
    if start:
        matching = matching.where(Version.published >= datetime.combine(start, time.min, ISTANBUL).astimezone(UTC))
    if end:
        matching = matching.where(Version.published <= datetime.combine(end, time.max, ISTANBUL).astimezone(UTC))
    member_count = select(func.count()).where(Member.cluster_id == Cluster.id).correlate(Cluster).scalar_subquery()
    demo = (select(func.count()).select_from(Member).join(Article, Article.id == Member.article_id)
            .join(Source, Source.id == Article.source_id)
            .where(Member.cluster_id == Cluster.id, Source.demo.is_(True)).correlate(Cluster).scalar_subquery())
    rows = db.execute(select(Cluster, member_count, demo).where(Cluster.id.in_(matching))
                      .order_by(Cluster.id.desc()).offset(offset).limit(51)).all()
    return {"items": [{**fields(c, "id", "title", "created_at"), "count": count, "demo": bool(example)}
                      for c, count, example in rows[:50]], "more": len(rows) > 50}


def links_view(db, version_ids):
    links = db.execute(select(Link, Source.demo).join(Version, Version.id == Link.version_id)
                       .join(Article, Article.id == Version.article_id)
                       .join(Source, Source.id == Article.source_id)
                       .where(Link.version_id.in_(version_ids)).order_by(Link.id)).all()
    targets = {}
    for article, demo in db.execute(select(Article, Source.demo).join(Source, Source.id == Article.source_id)
                                    .where(Article.url.in_({link.url for link, _ in links})).order_by(Article.id)):
        targets.setdefault((demo, article.url), []).append(article.id)
    return [{**fields(link, "id", "version_id", "url", "text", "context", "kind"),
             "target_ids": targets.get((demo, link.url), [])} for link, demo in links]


@app.get("/api/clusters/{cluster_id}")
def cluster(cluster_id: int, db=Depends(database)):
    item = db.get(Cluster, cluster_id)
    if item is None:
        raise HTTPException(404, "Grup bulunamadı.")
    rows = db.execute(article_query().where(Member.cluster_id == cluster_id)
                      .order_by(Version.published.asc().nulls_last(), Article.first_seen, Article.id)).all()
    articles = [article_view(*row) for row in rows]
    return {**fields(item, "id", "title", "created_at"), "articles": articles,
            "links": links_view(db, [v.id for _, _, v, _ in rows])}


@app.get("/api/articles")
def articles(decision: Literal["excluded"] = "excluded", db=Depends(database)):
    rows = db.execute(article_query().where(Member.decision == decision)
                      .order_by(Article.id.desc()).limit(100))
    return [article_view(*row) for row in rows]


@app.get("/api/articles/{article_id}")
def article(article_id: int, db=Depends(database)):
    row = get_article(db, article_id)
    versions = db.scalars(select(Version).where(Version.article_id == article_id)
                          .order_by(Version.id.desc())).all()
    return {**article_view(*row), "versions": [version_view(v, True) for v in versions],
            "links": links_view(db, [v.id for v in versions])}


@app.put("/api/articles/{article_id}/membership")
def membership(article_id: int, payload: DecisionInput, db=Depends(database)):
    analysis_lock(db)
    item, source, version, member = get_article(db, article_id)
    old_group = member.cluster_id if member else None
    if payload.decision == "excluded":
        if payload.cluster_id is not None:
            raise HTTPException(422, "Gruptan çıkarırken grup kimliği gönderilmez.")
        target = None
    elif payload.decision == "confirmed":
        if not member or not member.cluster_id or payload.cluster_id is not None:
            raise HTTPException(422, "Mevcut bir grup üyeliği onaylanabilir.")
        target = member.cluster_id
    elif payload.cluster_id is None:
        group = Cluster(title=version.title or "(Başlıksız)")
        db.add(group)
        db.flush()
        target = group.id
    else:
        target = payload.cluster_id
        target_row = db.execute(article_query().where(Member.cluster_id == target).limit(1)).first()
        if not target_row:
            raise HTTPException(404, "Etkin hedef grup bulunamadı.")
        if target_row[1].demo != source.demo:
            raise HTTPException(409, "Örnek ve gerçek haberler aynı gruba taşınamaz.")
    if not member:
        member = Member(article_id=item.id)
        db.add(member)
    member.cluster_id, member.decision = target, payload.decision
    member.method, member.score = "manual-v1", None
    membership_event(db, version, old_group, target)
    db.commit()
    return fields(member, "cluster_id", "decision", "method", "score")


@app.get("/api/compare")
def compare(left: int, right: int, db=Depends(database)):
    if left == right:
        raise HTTPException(422, "İki farklı haber seçin.")
    a, b = get_article(db, left)[2], get_article(db, right)[2]
    docs, vectors = matrices([a, b])
    value, method = score(a, b, *docs, vectors[0], vectors[1])
    excerpts = []
    for version in (a, b):
        raw = (version.body or version.summary or version.title).split()[:2500]
        excerpts.append([(word, normalize(word)) for word in raw if normalize(word)])
    l, r = excerpts
    matcher = SequenceMatcher(None, [x[1] for x in l], [x[1] for x in r], autojunk=True)
    blocks = sorted((block for block in matcher.get_matching_blocks() if block.size >= 5),
                    key=lambda block: -block.size)[:8]
    return {"score": value, "method": method, "analysis_version": METHOD, "threshold": THRESHOLD,
            "left": version_view(a, True), "right": version_view(b, True),
            "segments": [{"left": " ".join(w for w, _ in l[i:i+n]),
                          "right": " ".join(w for w, _ in r[j:j+n])} for i, j, n in blocks]}

