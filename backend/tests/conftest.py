import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.api import app
from app.db import Base, Session, engine as default_engine


@pytest.fixture
def fixtures():
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def database():
    url = os.getenv("TEST_DATABASE_URL")
    admin = None
    if url:
        schema = "haber_test_" + uuid4().hex
        admin = create_engine(url, isolation_level="AUTOCOMMIT")
        with admin.connect() as connection:
            connection.exec_driver_sql(f"CREATE SCHEMA {schema}")
        engine = create_engine(url, connect_args={"options": f"-c search_path={schema}"})
    else:
        engine = create_engine("sqlite://", poolclass=StaticPool,
                               connect_args={"check_same_thread": False})
    Session.configure(bind=engine)
    try:
        Base.metadata.create_all(engine)
        yield engine
    finally:
        Session.configure(bind=default_engine)
        engine.dispose()
        if admin:
            with admin.connect() as connection:
                connection.exec_driver_sql(f"DROP SCHEMA {schema} CASCADE")
            admin.dispose()


@pytest.fixture
def api(database):
    with TestClient(app, base_url="http://localhost") as client:
        yield client

