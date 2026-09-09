import subprocess
import sys
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db.session import get_session
from app.main import app


def test_health_does_not_need_database(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "payload",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "a" * 121},
        {"name": "valid", "description": "x" * 2001},
        {"name": "ok", "unknown": 1},
        {"description": "missing name"},
        {"name": 123},
    ],
)
def test_validation(client, payload):
    response = client.post("/api/projects", json=payload)
    assert response.status_code == 422
    assert "input" not in response.json()["detail"][0]


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1"])
def test_invalid_pagination(client, query):
    assert client.get("/api/projects?" + query).status_code == 422


def test_database_failure_is_safe_and_health_stays_live(client):
    session = MagicMock()
    session.execute.side_effect = OperationalError(
        "secret SQL", {}, Exception("secret password")
    )
    app.dependency_overrides[get_session] = lambda: session
    response = client.get("/api/ready")
    assert response.status_code == 503
    assert "secret" not in response.text
    assert client.get("/api/health").status_code == 200


def test_explicit_cors(client):
    good = client.options(
        "/api/projects",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert good.headers["access-control-allow-origin"] == "http://localhost:5173"
    bad = client.options(
        "/api/projects",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in bad.headers


def test_postgres_create_list_and_ready(db_client):
    assert db_client.get("/api/ready").status_code == 200
    assert db_client.get("/api/projects").json()["total"] == 0
    created = db_client.post(
        "/api/projects",
        json={"name": "  Research  ", "description": "  A real project  "},
    )
    assert created.status_code == 201
    data = created.json()
    assert data["name"] == "Research"
    assert data["description"] == "A real project"
    assert data["id"] and data["created_at"].endswith("Z")
    db_client.post("/api/projects", json={"name": "Another"})
    first = db_client.get("/api/projects?limit=1").json()
    second = db_client.get("/api/projects?limit=1&offset=1").json()
    assert first["total"] == 2
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert db_client.get("/api/projects?offset=2").json()["items"] == []


def test_migration_matches_models_and_round_trip(database):
    engine, env = database
    subprocess.run([sys.executable, "-m", "alembic", "check"], env=env, check=True)
    # The fixture has verified this is a fresh, isolated test database.
    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"], env=env, check=True
    )
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('public.projects')")) is None
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True
    )


def test_milestone_one_upgrade_preserves_project(database):
    from uuid import uuid4

    engine, env = database
    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0001"], env=env, check=True
    )
    project_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO projects (id,name,description) VALUES (:id, :name, :description)"
            ),
            {
                "id": project_id,
                "name": "Before 2A",
                "description": "Preserved upgrade data",
            },
        )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True
    )
    with engine.begin() as connection:
        assert (
            connection.scalar(
                text("SELECT name FROM projects WHERE id=:id"), {"id": project_id}
            )
            == "Before 2A"
        )
        connection.execute(
            text("DELETE FROM projects WHERE id=:id"), {"id": project_id}
        )
