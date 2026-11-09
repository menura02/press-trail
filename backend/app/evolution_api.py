from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from .analysis import analysis_lock
from .db import database, now
from .evolution_models import Annotation, ClaimPair, Finding, Notification, VersionDiff, Watch
from .models import Article, Cluster, Member, Source, Version
from .research import MANUAL, diff_for, pair_for, save_finding

router = APIRouter(prefix="/api")
Review = Literal["pending", "confirmed", "rejected"]
NoteKind = Literal["article", "version", "diff", "finding"]
WatchKind = Literal["article", "cluster"]
Offset = Query(default=0, ge=0, le=1000000)
Limit = Query(default=20, ge=1, le=100)


def require(db, model, identity):
    item = db.get(model, identity)
    if item is None:
        raise HTTPException(404, "Araştırma kaydı bulunamadı.")
    return item


def fields(row, *keys):
    return {key: getattr(row, key) for key in keys}


def page(db, statement, offset, limit, view):
    rows = db.scalars(statement.offset(offset).limit(limit + 1)).all()
    return {"items": [view(row) for row in rows[:limit]], "more": len(rows) > limit}


def evidence(version):
    return fields(version, "id", "article_id", "title", "published", "published_raw", "published_state",
                  "collected_at", "scope", "extractor")


def diff_view(db, row):
    return {**fields(row, "id", "article_id", "method", "created_at", "completed_at", "result"),
            "before": evidence(db.get(Version, row.before_id)), "after": evidence(db.get(Version, row.after_id))}


def finding_view(db, finding):
    version = db.get(Version, finding.version_id)
    article = db.get(Article, version.article_id)
    source = db.get(Source, article.source_id)
    return {**fields(finding, "id", "kind", "field", "start", "end", "quote", "context", "signals",
                     "method", "status", "created_at", "updated_at"),
            "version": evidence(version), "source": source.name, "url": article.url, "demo": source.demo}


def pair_view(db, row):
    left, right = db.get(Finding, row.left_id), db.get(Finding, row.right_id)
    current = all((member := db.get(Member, db.get(Version, item.version_id).article_id)) is not None
                  and member.cluster_id == row.cluster_id for item in (left, right))
    return {**fields(row, "id", "cluster_id", "method", "status", "created_at", "updated_at"),
            "left": finding_view(db, left), "right": finding_view(db, right), "current_group": current}


class DiffInput(BaseModel):
    before_id: int = Field(gt=0)
    after_id: int = Field(gt=0)


@router.post("/articles/{article_id}/diffs")
def request_diff(article_id: int, payload: DiffInput, db=Depends(database)):
    analysis_lock(db)
    require(db, Article, article_id)
    before, after = (require(db, Version, key) for key in (payload.before_id, payload.after_id))
    if before.id == after.id or any(v.article_id != article_id for v in (before, after)):
        raise HTTPException(422, "Aynı haberin iki farklı sürümünü seçin.")
    item = diff_for(db, before, after)
    db.commit()
    return {"id": item.id, "pending": item.completed_at is None}


@router.get("/diffs/{diff_id}")
def get_diff(diff_id: int, db=Depends(database)):
    return diff_view(db, require(db, VersionDiff, diff_id))


@router.get("/clusters/{cluster_id}/diffs")
def group_diffs(cluster_id: int, offset: int = Offset, limit: int = Limit, db=Depends(database)):
    require(db, Cluster, cluster_id)
    query = (select(VersionDiff).join(Member, Member.article_id == VersionDiff.article_id)
             .where(Member.cluster_id == cluster_id, VersionDiff.completed_at.is_not(None))
             .order_by(VersionDiff.id.desc()))
    return page(db, query, offset, limit, lambda row: {
        **fields(row, "id", "article_id", "before_id", "after_id"),
        "title": db.get(Version, row.after_id).title,
    })


class NoteInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    text: str = Field(min_length=1, max_length=10000)
    tags: list[str] = Field(default_factory=list, max_length=12)
    status: Literal["open", "reviewed", "resolved"] = "open"

    @field_validator("tags")
    @classmethod
    def check_tags(cls, items):
        tags = list(dict.fromkeys(tag.strip() for tag in items if tag.strip()))
        if any(len(tag) > 40 or "\x00" in tag for tag in tags):
            raise ValueError("Etiket en çok 40 karakter içerebilir.")
        return tags

    @field_validator("text")
    @classmethod
    def check_text(cls, value):
        if "\x00" in value:
            raise ValueError("Not geçersiz karakter içeriyor.")
        return value


def note_view(note):
    return fields(note, "id", "target_kind", "target_id", "text", "tags", "status", "created_at", "updated_at")


@router.get("/annotations/{kind}/{target_id}")
def notes(kind: NoteKind, target_id: int, offset: int = Offset, limit: int = Limit, db=Depends(database)):
    require(db, NOTE_MODELS[kind], target_id)
    query = select(Annotation).where(Annotation.target_kind == kind, Annotation.target_id == target_id)
    return page(db, query.order_by(Annotation.id.desc()), offset, limit, note_view)


NOTE_MODELS = {"article": Article, "version": Version, "diff": VersionDiff, "finding": Finding}
WATCH_MODELS = {"article": Article, "cluster": Cluster}


@router.post("/annotations/{kind}/{target_id}", status_code=201)
def create_note(kind: NoteKind, target_id: int, payload: NoteInput, db=Depends(database)):
    require(db, NOTE_MODELS[kind], target_id)
    note = Annotation(target_kind=kind, target_id=target_id, **payload.model_dump())
    db.add(note)
    db.commit()
    return note_view(note)


@router.put("/annotations/{note_id}")
def edit_note(note_id: int, payload: NoteInput, db=Depends(database)):
    note = require(db, Annotation, note_id)
    for key, value in payload.model_dump().items():
        setattr(note, key, value)
    note.updated_at = now()
    db.commit()
    return note_view(note)


@router.delete("/annotations/{note_id}", status_code=204)
def delete_note(note_id: int, db=Depends(database)):
    db.delete(require(db, Annotation, note_id))
    db.commit()
    return Response(status_code=204)


def watch_query(kind, identity):
    return select(Watch).where(Watch.target_kind == kind, Watch.target_id == identity)


@router.get("/watch/{kind}/{target_id}")
def get_watch(kind: WatchKind, target_id: int, db=Depends(database)):
    require(db, WATCH_MODELS[kind], target_id)
    return {"watching": db.scalar(watch_query(kind, target_id)) is not None}


class WatchInput(BaseModel):
    watching: bool


@router.put("/watch/{kind}/{target_id}")
def set_watch(kind: WatchKind, target_id: int, payload: WatchInput, db=Depends(database)):
    analysis_lock(db)
    require(db, WATCH_MODELS[kind], target_id)
    item = db.scalar(watch_query(kind, target_id))
    if payload.watching and item is None:
        db.add(Watch(target_kind=kind, target_id=target_id))
    elif not payload.watching and item is not None:
        db.delete(item)
    db.commit()
    return {"watching": payload.watching}


@router.get("/watch")
def watchlist(offset: int = Offset, limit: int = Limit, db=Depends(database)):
    def view(item):
        target = db.get(WATCH_MODELS[item.target_kind], item.target_id)
        title = target.title if item.target_kind == "cluster" else db.scalar(
            select(Version.title).where(Version.article_id == item.target_id).order_by(Version.id.desc()).limit(1))
        return {**fields(item, "id", "target_kind", "target_id", "created_at"), "title": title}
    return page(db, select(Watch).order_by(Watch.id.desc()), offset, limit, view)


def notification_view(row):
    return fields(row, "id", "kind", "article_id", "cluster_id", "version_id", "diff_id", "finding_id",
                  "title", "cluster_title", "created_at", "read_at")


@router.get("/notifications")
def notifications(unread: bool = False, offset: int = Offset, limit: int = Limit, db=Depends(database)):
    statement = select(Notification).order_by(Notification.id.desc())
    if unread:
        statement = statement.where(Notification.read_at.is_(None))
    return page(db, statement, offset, limit, notification_view)


class ReadInput(BaseModel):
    read: bool


@router.put("/notifications/{notification_id}")
def read_notification(notification_id: int, payload: ReadInput, db=Depends(database)):
    row = require(db, Notification, notification_id)
    row.read_at = (row.read_at or now()) if payload.read else None
    db.commit()
    return notification_view(row)


class SelectionInput(BaseModel):
    field: Literal["title", "summary", "body"]
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=2400)


class ReviewInput(BaseModel):
    status: Review


@router.get("/versions/{version_id}/findings")
def version_findings(version_id: int, offset: int = Offset, limit: int = Limit, db=Depends(database)):
    require(db, Version, version_id)
    return page(db, select(Finding).where(Finding.version_id == version_id).order_by(
        Finding.kind.desc(), Finding.id.desc()), offset, limit, lambda row: finding_view(db, row))


@router.post("/versions/{version_id}/findings", status_code=201)
def manual_finding(version_id: int, payload: SelectionInput, db=Depends(database)):
    analysis_lock(db)
    version = require(db, Version, version_id)
    value = getattr(version, payload.field)
    if (payload.end > len(value) or payload.start >= payload.end or not payload.quote.strip()
            or value[payload.start:payload.end] != payload.quote):
        raise HTTPException(422, "Alıntı, seçilen sürümün belirtilen metin aralığıyla eşleşmiyor.")
    row, _ = save_finding(db, version, "claim", payload.field, payload.start, payload.end, MANUAL)
    db.commit()
    return finding_view(db, row)


@router.get("/findings/{finding_id}")
def get_finding(finding_id: int, db=Depends(database)):
    return finding_view(db, require(db, Finding, finding_id))


@router.put("/findings/{finding_id}/review")
def review_finding(finding_id: int, payload: ReviewInput, db=Depends(database)):
    row = require(db, Finding, finding_id)
    row.status, row.updated_at = payload.status, now()
    db.commit()
    return finding_view(db, row)


@router.get("/clusters/{cluster_id}/claims")
def group_claims(cluster_id: int, kind: Literal["claim", "correction"] = "claim",
                 offset: int = Offset, limit: int = Limit, db=Depends(database)):
    require(db, Cluster, cluster_id)
    query = (select(Finding).join(Version, Version.id == Finding.version_id)
             .join(Member, Member.article_id == Version.article_id)
             .where(Member.cluster_id == cluster_id, Finding.kind == kind).order_by(Finding.id.desc()))
    return page(db, query, offset, limit, lambda row: finding_view(db, row))


@router.get("/clusters/{cluster_id}/claim-comparisons")
def group_pairs(cluster_id: int, offset: int = Offset, limit: int = Limit, db=Depends(database)):
    require(db, Cluster, cluster_id)
    return page(db, select(ClaimPair).where(ClaimPair.cluster_id == cluster_id).order_by(
        ClaimPair.id.desc()), offset, limit, lambda row: pair_view(db, row))


class PairInput(BaseModel):
    left_id: int = Field(gt=0)
    right_id: int = Field(gt=0)


@router.post("/clusters/{cluster_id}/claim-comparisons")
def create_pair(cluster_id: int, payload: PairInput, db=Depends(database)):
    analysis_lock(db)
    require(db, Cluster, cluster_id)
    article_ids = []
    for key in (payload.left_id, payload.right_id):
        item = require(db, Finding, key)
        version = db.get(Version, item.version_id)
        member = db.get(Member, version.article_id)
        if item.kind != "claim" or member is None or member.cluster_id != cluster_id:
            raise HTTPException(422, "İki iddia da bu grubun üye haberlerine ait olmalı.")
        article_ids.append(version.article_id)
    if article_ids[0] == article_ids[1]:
        raise HTTPException(422, "İki farklı haberden iddia seçin.")
    row = pair_for(db, cluster_id, payload.left_id, payload.right_id, MANUAL)
    db.commit()
    return pair_view(db, row)


@router.put("/claim-comparisons/{pair_id}/review")
def review_pair(pair_id: int, payload: ReviewInput, db=Depends(database)):
    row = require(db, ClaimPair, pair_id)
    row.status, row.updated_at = payload.status, now()
    db.commit()
    return pair_view(db, row)

