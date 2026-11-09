from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, now


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    url: Mapped[str] = mapped_column(unique=True)
    language: Mapped[str] = mapped_column(default="tr")
    active: Mapped[bool] = mapped_column(default=True)
    full_text: Mapped[bool] = mapped_column(default=False)
    interval_minutes: Mapped[int] = mapped_column(default=60)
    next_check: Mapped[datetime] = mapped_column(default=now, index=True)
    etag: Mapped[str | None]
    modified: Mapped[str | None]
    demo: Mapped[bool] = mapped_column(default=False)
    revision: Mapped[int] = mapped_column(default=0)


class Run(Base):
    __tablename__ = "fetch_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    status: Mapped[str] = mapped_column(default="queued")
    created_at: Mapped[datetime] = mapped_column(default=now)
    available_at: Mapped[datetime] = mapped_column(default=now)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    lease_until: Mapped[datetime | None]
    token: Mapped[str | None] = mapped_column(String(32))
    attempts: Mapped[int] = mapped_column(default=0)
    seen: Mapped[int] = mapped_column(default=0)
    versions: Mapped[int] = mapped_column(default=0)
    skipped: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None]
    __table_args__ = (
        Index("ix_run_claim", "status", "available_at", "lease_until"),
        Index("uq_source_pending", "source_id", unique=True,
              postgresql_where=text("status IN ('queued','running')"),
              sqlite_where=text("status IN ('queued','running')")),
    )


class Article(Base):
    __tablename__ = "articles"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    url: Mapped[str]
    feed_id: Mapped[str | None]
    feed_url: Mapped[str | None]
    first_seen: Mapped[datetime] = mapped_column(default=now)
    __table_args__ = (
        UniqueConstraint("source_id", "url"),
        Index("ix_article_feed_id", "source_id", "feed_id"),
    )


class Version(Base):
    __tablename__ = "article_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), index=True)
    title: Mapped[str]
    summary: Mapped[str]
    body: Mapped[str]
    digest: Mapped[str]
    fingerprint: Mapped[str]
    published: Mapped[datetime | None]
    updated: Mapped[datetime | None]
    published_raw: Mapped[str | None]
    updated_raw: Mapped[str | None]
    published_state: Mapped[str]
    updated_state: Mapped[str]
    collected_at: Mapped[datetime] = mapped_column(default=now)
    scope: Mapped[str]
    extractor: Mapped[str]
    evolution_method: Mapped[str | None] = mapped_column(index=True)


class Link(Base):
    __tablename__ = "article_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("article_versions.id"), index=True)
    url: Mapped[str] = mapped_column(index=True)
    text: Mapped[str]
    context: Mapped[str]
    kind: Mapped[str]


class Cluster(Base):
    __tablename__ = "clusters"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=now, index=True)


class Member(Base):
    __tablename__ = "cluster_members"
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), primary_key=True)
    cluster_id: Mapped[int | None] = mapped_column(ForeignKey("clusters.id"), index=True)
    decision: Mapped[str]
    method: Mapped[str]
    score: Mapped[float | None]

