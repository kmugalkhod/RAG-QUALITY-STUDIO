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


def test_milestone_two_a_upgrade_preserves_chunks(database):
    from uuid import uuid4
    from sqlalchemy.orm import Session
    from app.models.project import Project
    from app.models.document import Document, ProcessingRun, Chunk

    engine, env = database
    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0002"], env=env, check=True
    )
    p, d, r = uuid4(), uuid4(), uuid4()
    with Session(engine) as session:
        session.add(Project(id=p, name="Before 2B", description="Upgrade fixture"))
        session.flush()
        session.add(
            Document(
                id=d,
                project_id=p,
                filename="source.txt",
                storage_name=uuid4().hex,
                media_type="text/plain",
                content_hash="a" * 64,
                size_bytes=4,
            )
        )
        session.flush()
        session.add(
            ProcessingRun(
                id=r,
                document_id=d,
                version=1,
                chunk_size=4,
                overlap=0,
                parser_version="test",
                status="succeeded",
                chunk_count=1,
            )
        )
        session.flush()
        session.add(Chunk(run_id=r, ordinal=0, start_char=0, end_char=4, text="kept"))
        session.commit()
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True
    )
    with Session(engine) as session:
        chunk = session.get(Chunk, (r, 0))
        assert chunk.text == "kept"
        assert session.get(ProcessingRun, r).status == "succeeded"
        session.delete(chunk)
        session.flush()
        session.delete(session.get(ProcessingRun, r))
        session.flush()
        session.delete(session.get(Document, d))
        session.flush()
        session.delete(session.get(Project, p))
        session.commit()


def test_pipeline_kind_upgrade_backfills_existing_rows(database):
    import json
    from uuid import uuid4

    engine, env = database
    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0007"], env=env, check=True
    )
    project_id, pipeline_id, version_id = uuid4(), uuid4(), uuid4()
    execution = {
        "schema_version": 1,
        "nodes": [],
        "edges": [],
    }
    layout = {"positions": {}}
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO projects (id, name, description) "
                "VALUES (:id, :name, :description)"
            ),
            {
                "id": project_id,
                "name": "Pipeline kind upgrade",
                "description": "Legacy populated migration fixture",
            },
        )
        connection.execute(
            text(
                "INSERT INTO pipelines (id, project_id, name) VALUES (:id, :project, :name)"
            ),
            {"id": pipeline_id, "project": project_id, "name": "Legacy answer"},
        )
        connection.execute(
            text(
                "INSERT INTO pipeline_versions "
                "(id, pipeline_id, project_id, version, name, execution, layout) "
                "VALUES (:id, :pipeline, :project, 1, :name, "
                "CAST(:execution AS jsonb), CAST(:layout AS jsonb))"
            ),
            {
                "id": version_id,
                "pipeline": pipeline_id,
                "project": project_id,
                "name": "Legacy answer",
                "execution": json.dumps(execution),
                "layout": json.dumps(layout),
            },
        )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True
    )
    with engine.begin() as connection:
        assert (
            connection.scalar(
                text("SELECT kind FROM pipelines WHERE id=:id"), {"id": pipeline_id}
            )
            == "answer"
        )
        assert (
            connection.scalar(
                text("SELECT id FROM pipeline_versions WHERE id=:id"),
                {"id": version_id},
            )
            == version_id
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_constraint "
                    "WHERE conname='ck_pipeline_kind'"
                )
            )
            == 1
        )
    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0007"], env=env, check=True
    )
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT id FROM pipeline_versions WHERE id=:id"),
                {"id": version_id},
            )
            == version_id
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_name='pipelines' AND column_name='kind'"
                )
            )
            == 0
        )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True
    )
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT kind FROM pipelines WHERE id=:id"), {"id": pipeline_id}
            )
            == "answer"
        )
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM pipeline_versions WHERE id=:id"), {"id": version_id}
        )
        connection.execute(
            text("DELETE FROM pipelines WHERE id=:id"), {"id": pipeline_id}
        )
        connection.execute(
            text("DELETE FROM projects WHERE id=:id"), {"id": project_id}
        )
