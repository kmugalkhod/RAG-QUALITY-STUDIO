import os
import subprocess
import sys
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.db.session import get_session
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "Set TEST_DATABASE_URL to a dedicated PostgreSQL database ending in _test"
        )
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not (
        parsed.database or ""
    ).endswith("_test"):
        pytest.fail(
            "Integration tests require PostgreSQL and a dedicated database ending in _test"
        )
    engine = create_engine(url, isolation_level="REPEATABLE READ")
    with engine.connect() as connection:
        if connection.scalar(text("SELECT to_regclass('public.projects')")):
            pytest.fail(
                "Test database must be empty; no existing project table will be reset"
            )
    env = {**os.environ, "DATABASE_URL": url}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True
    )
    yield engine, env
    engine.dispose()


@pytest.fixture
def db_client(database, client):
    engine, _ = database
    with engine.connect() as connection:
        transaction = connection.begin()

        def session_override():
            with Session(
                bind=connection, join_transaction_mode="create_savepoint"
            ) as session:
                yield session

        app.dependency_overrides[get_session] = session_override
        yield client
        transaction.rollback()
