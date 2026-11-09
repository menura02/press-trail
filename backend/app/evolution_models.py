from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, now


class VersionDiff(Base):
    __tablename__ = "version_diffs"
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), index=True)
    before_id: Mapped[int] = mapped_column(ForeignKey("article_versions.id"))
    after_id: Mapped[int] = mapped_column(ForeignKey("article_versions.id"))
    method: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=now)
    completed_at: Mapped[datetime | None]
    __table_args__ = (
        UniqueConstraint("before_id", "after_id", "method"),
        CheckConstraint("before_id < after_id", name="ck_diff_order"),
        Index("ix_diff_pending", "completed_at", "id"),
    )


class Finding(Base):
    __tablename__ = "claim_candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("article_versions.id"))
    kind: Mapped[str] = mapped_column(String(16))
    field: Mapped[str] = mapped_column(String(16))
    start: Mapped[int]
    end: Mapped[int]
    quote: Mapped[str] = mapped_column(Text)
    context: Mapped[str] = mapped_column(Text)
    signals: Mapped[dict] = mapped_column(JSON)
    method: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(default=now)
    updated_at: Mapped[datetime] = mapped_column(default=now)
    __table_args__ = (
        UniqueConstraint("version_id", "kind", "field", "start", "end"),
        CheckConstraint('start >= 0 AND start < "end"', name="ck_finding_range"),
        Index("ix_finding_version_kind", "version_id", "kind", "id"),
    )


class ClaimPair(Base):
    __tablename__ = "claim_comparisons"
    id: Mapped[int] = mapped_column(primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("clusters.id"), index=True)
    left_id: Mapped[int] = mapped_column(ForeignKey("claim_candidates.id"))
    right_id: Mapped[int] = mapped_column(ForeignKey("claim_candidates.id"))
    method: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(default=now)
    updated_at: Mapped[datetime] = mapped_column(default=now)
    __table_args__ = (
        UniqueConstraint("cluster_id", "left_id", "right_id"),
        CheckConstraint("left_id < right_id", name="ck_claim_pair_order"),
    )


class Annotation(Base):
    __tablename__ = "annotations"
    id: Mapped[int] = mapped_column(primary_key=True)
    target_kind: Mapped[str] = mapped_column(String(16))
    target_id: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(default=now)
    updated_at: Mapped[datetime] = mapped_column(default=now)
    __table_args__ = (Index("ix_annotation_target", "target_kind", "target_id", "id"),)


class Watch(Base):
    __tablename__ = "watchlist_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    target_kind: Mapped[str] = mapped_column(String(16))
    target_id: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=now)
    __table_args__ = (UniqueConstraint("target_kind", "target_id"),)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_key: Mapped[str] = mapped_column(String(120), unique=True)
    kind: Mapped[str] = mapped_column(String(24))
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"))
    cluster_id: Mapped[int | None] = mapped_column(ForeignKey("clusters.id"))
    version_id: Mapped[int] = mapped_column(ForeignKey("article_versions.id"))
    diff_id: Mapped[int | None] = mapped_column(ForeignKey("version_diffs.id"))
    finding_id: Mapped[int | None] = mapped_column(ForeignKey("claim_candidates.id"))
    title: Mapped[str] = mapped_column(Text)
    cluster_title: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=now)
    read_at: Mapped[datetime | None]
    __table_args__ = (Index("ix_notification_unread", "read_at", "id"),)

