from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import and_, or_, select

from .db import Session, now
from .models import Run, Source

MAX_ATTEMPTS = 3
LEASE = timedelta(minutes=5)
PENDING = ("queued", "running")


@dataclass(frozen=True)
class Claim:
    id: int
    source_id: int
    token: str


def enqueue(db, source):
    # Caller holds the source row lock.
    run = db.scalar(select(Run).where(Run.source_id == source.id, Run.status.in_(PENDING)))
    if run is None:
        run = Run(source_id=source.id)
        db.add(run)
        db.flush()
    return run


def schedule():
    at = now()
    with Session.begin() as db:
        for source in db.scalars(select(Source).where(
            Source.active.is_(True), Source.demo.is_(False), Source.next_check <= at
        ).order_by(Source.id).limit(20).with_for_update(skip_locked=True)):
            enqueue(db, source)
            source.next_check = at + timedelta(minutes=source.interval_minutes)


def claim():
    at = now()
    with Session.begin() as db:
        expired = and_(Run.status == "running", Run.lease_until <= at)
        for run in db.scalars(select(Run).where(expired, Run.attempts >= MAX_ATTEMPTS)
                              .with_for_update(skip_locked=True)):
            run.status, run.error, run.finished_at = "failed", "lease_expired", at
            run.token, run.lease_until = None, None
        run = db.scalar(select(Run).join(Source, Source.id == Run.source_id).where(
            Run.attempts < MAX_ATTEMPTS,
            or_(and_(Run.status == "queued", Run.available_at <= at), expired)
        ).order_by(Run.id).limit(1).with_for_update(skip_locked=True, of=Run))
        if run is None:
            return None
        run.status = "running"
        run.started_at = run.started_at or at
        run.attempts += 1
        run.token = uuid4().hex
        run.lease_until = at + LEASE
        return Claim(run.id, run.source_id, run.token)


def owned(db, job):
    return db.scalar(select(Run).where(
        Run.id == job.id, Run.status == "running", Run.token == job.token, Run.lease_until > now()
    ).with_for_update())


def renew(job, revision):
    with Session.begin() as db:
        source = db.get(Source, job.source_id, with_for_update=True)
        run = owned(db, job)
        if run is None:
            return False
        if not source.active or source.revision != revision:
            finish(run, "cancelled")
            return False
        run.lease_until = now() + LEASE
        return True


def finish(run, status, error=None):
    run.status, run.error, run.finished_at = status, error, now()
    run.token, run.lease_until = None, None


def fail(job, kind):
    with Session.begin() as db:
        run = owned(db, job)
        if run is None:
            return
        if run.attempts < MAX_ATTEMPTS and kind in {"http_retry", "dns", "transport", "timeout", "internal"}:
            run.status, run.error = "queued", kind
            run.available_at = now() + timedelta(seconds=30 * 2 ** (run.attempts - 1))
            run.token, run.lease_until = None, None
        else:
            finish(run, "failed", kind)

