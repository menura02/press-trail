import os
from datetime import UTC, datetime

from sqlalchemy import DateTime, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def now():
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {datetime: UTCDateTime()}


engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///./haber.db"), pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)


def database():
    with Session() as db:
        yield db

