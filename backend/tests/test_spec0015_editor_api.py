"""Spec 0015 U3 and U4: pipelines open by their saved kind, and runs say which
extract, clean and chunk versions they used."""

from types import SimpleNamespace
from uuid import uuid4

from app.services.ingestion import _stage_versions
from test_existing_files_ingestion import ingestion_draft as files_draft
from test_ingestion_contracts import ingestion_draft
from test_pipelines import draft, pipeline_api  # noqa: F401
from test_queries import query_api  # noqa: F401
from test_indexes import index_api, embedding_config  # noqa: F401
from test_documents import documents_api  # noqa: F401

CONFIG = SimpleNamespace(
    provider="openrouter",
    model="openai/text-embedding-3-small",
    dimensions=1536,
    revision="1",
)


def test_a_pipeline_is_read_by_id_with_its_saved_kind(pipeline_api):  # noqa: F811
    from app.core.config import settings

    c, _, p, q, index = pipeline_api
    base = f"/api/projects/{p}/pipelines"
    answer = c.post(base, json=draft(index["id"])).json()
    ingestion_payload = ingestion_draft()
    embed = next(
        n for n in ingestion_payload["execution"]["nodes"] if n["type"] == "embed"
    )
    embed.update(
        provider=settings.embedding_provider,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        config_version=settings.embedding_revision,
    )
    ingestion = c.post(base, json=ingestion_payload)
    assert ingestion.status_code == 201, ingestion.text
    ingestion = ingestion.json()

    read = c.get(f"{base}/{answer['pipeline_id']}")
    assert read.status_code == 200, read.text
    assert read.json()["kind"] == "answer"
    assert read.json()["name"] == "Evidence pipeline"
    assert c.get(f"{base}/{ingestion['pipeline_id']}").json()["kind"] == "ingestion"
    # Another project's pipeline, an unknown ID and a malformed ID are not found.
    assert c.get(f"{base.replace(p, q)}/{answer['pipeline_id']}").status_code == 404
    missing = c.get(f"{base}/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Pipeline not found in this project."
    assert c.get(f"{base}/not-a-pipeline").status_code == 422
    # The fixed routes keep their meaning.
    assert c.get(f"{base}/options").status_code == 200


def test_stage_versions_list_each_saved_version_once():
    payload = files_draft(
        [str(uuid4())],
        CONFIG,
        schema_version=2,
        clean_steps=None,
        chunk_settings={
            "algorithm": "section_token",
            "config_version": "section-token-v5",
        },
    )
    assert _stage_versions(payload["execution"]) == {
        "extract": ["native-text-v1"],
        "clean": ["deterministic-clean-v1"],
        "chunk": ["section-token-v5"],
    }


def test_a_saved_chunker_without_a_version_reports_v1():
    payload = files_draft(
        [str(uuid4())],
        CONFIG,
        schema_version=2,
        chunk_settings={"algorithm": "parent_child"},
    )
    assert _stage_versions(payload["execution"])["chunk"] == ["parent-child-v1"]


def test_unreadable_snapshots_have_no_stage_versions():
    assert _stage_versions(None) is None
    assert _stage_versions({"schema_version": 9, "nodes": []}) is None


def _ingestion_payload(name):
    from app.core.config import settings

    payload = ingestion_draft()
    payload["name"] = name
    embed = next(n for n in payload["execution"]["nodes"] if n["type"] == "embed")
    embed.update(
        provider=settings.embedding_provider,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        config_version=settings.embedding_revision,
    )
    return payload


def test_pipeline_list_shows_last_run_and_index_and_filters(pipeline_api):  # noqa: F811
    from datetime import datetime, timedelta, timezone
    from uuid import UUID

    from sqlalchemy import delete
    from sqlalchemy.orm import Session

    from app.models.index import IndexVersion, KnowledgeSet
    from app.models.ingestion import IngestionRun

    c, engine, p, q, index = pipeline_api
    base = f"/api/projects/{p}/pipelines"
    saved = {}
    for name in ("Census rows", "GAO tables", "Harbor site", "Never run_%"):
        response = c.post(base, json=_ingestion_payload(name))
        assert response.status_code == 201, response.text
        saved[name] = response.json()
    second = c.post(
        f"{base}/{saved['Census rows']['pipeline_id']}/versions",
        json=_ingestion_payload("Census rows"),
    ).json()
    answer = c.post(base, json=draft(index["id"])).json()
    start = datetime.now(timezone.utc) - timedelta(hours=1)
    with Session(engine) as session:
        knowledge = KnowledgeSet(project_id=UUID(p), name="Census index")
        session.add(knowledge)
        session.flush()

        def run(version, status, minutes, failed=0):
            row = IngestionRun(
                project_id=UUID(p),
                pipeline_version_id=UUID(version["id"]),
                knowledge_set_id=knowledge.id,
                status=status,
                stage="complete" if status == "succeeded" else "processing",
                progress=100 if status == "succeeded" else 50,
                published_count=1 if status == "succeeded" else 0,
                discovered_count=1 + failed,
                processed_count=1 if status == "succeeded" else 0,
                failed_count=failed,
                snapshot={},
                created_at=start + timedelta(minutes=minutes),
                finished_at=start + timedelta(minutes=minutes + 1),
            )
            session.add(row)
            session.flush()
            return row

        old = run(saved["Census rows"], "succeeded", 0)
        session.add(
            IndexVersion(
                project_id=UUID(p),
                knowledge_set_id=knowledge.id,
                ingestion_run_id=old.id,
                version=1,
                dimensions=index["embedding_config"]["dimensions"],
                embedding_config=index["embedding_config"],
                status="succeeded",
                chunk_count=1,
                embedded_count=1,
                attempts=1,
                failures=0,
            )
        )
        session.flush()
        knowledge.current_ready_index_id = session.scalar(select_index(knowledge.id))
        newest = run(second, "succeeded", 10, failed=1)
        run(saved["GAO tables"], "succeeded", 5)
        run(saved["GAO tables"], "failed", 20)
        run(saved["Harbor site"], "running", 30)
        session.commit()
        knowledge_id, newest_id = knowledge.id, newest.id

    try:
        page = c.get(f"{base}?kind=ingestion&limit=25").json()
        assert page["total"] == 4
        rows = {row["name"]: row for row in page["items"]}
        census = rows["Census rows"]
        assert census["latest_version"]["version"] == 2
        assert census["last_run"]["id"] == str(newest_id)
        assert census["last_run"]["pipeline_version"] == 2
        assert census["last_run"]["completion"] == "with_warnings"
        assert census["published_index"]["version"] == 1
        assert census["published_index"]["knowledge_set_name"] == "Census index"
        assert census["published_index"]["is_current"] is True
        assert rows["GAO tables"]["last_run"]["status"] == "failed"
        assert rows["GAO tables"]["published_index"] is None
        assert rows["Harbor site"]["last_run"]["status"] == "running"
        assert rows["Never run_%"]["last_run"] is None
        assert rows["Never run_%"]["latest_version"]["version"] == 1

        def names(query):
            return sorted(
                row["name"]
                for row in c.get(f"{base}?kind=ingestion&{query}").json()["items"]
            )

        assert names("outcome=complete") == ["Census rows"]
        assert names("outcome=failed") == ["GAO tables"]
        assert names("outcome=running") == ["Harbor site"]
        assert names("outcome=never_run") == ["Never run_%"]
        assert names("q=census") == ["Census rows"]
        assert names("q=%25") == ["Never run_%"]  # a literal %, not a wildcard
        assert names("q=_") == ["Never run_%"]
        assert names("q=rows&outcome=failed") == []
        assert c.get(f"{base}?outcome=other").status_code == 422
        # Newest first, paged.
        first = c.get(f"{base}?kind=ingestion&limit=2&offset=0").json()
        rest = c.get(f"{base}?kind=ingestion&limit=2&offset=2").json()
        assert first["total"] == rest["total"] == 4
        assert [r["name"] for r in first["items"] + rest["items"]] == [
            "Never run_%",
            "Harbor site",
            "GAO tables",
            "Census rows",
        ]
        # Answer rows carry their latest version; other projects see nothing.
        answer_row = c.get(f"{base}?kind=answer").json()["items"][0]
        assert answer_row["id"] == answer["pipeline_id"]
        assert answer_row["latest_version"]["version"] == 1
        assert answer_row["last_run"] is None
        assert c.get(f"/api/projects/{q}/pipelines?kind=ingestion").json()["total"] == 0
    finally:
        with Session(engine) as session:
            session.execute(
                delete(IndexVersion).where(
                    IndexVersion.knowledge_set_id == knowledge_id
                )
            )
            session.execute(
                delete(IngestionRun).where(IngestionRun.project_id == UUID(p))
            )
            session.execute(delete(KnowledgeSet).where(KnowledgeSet.id == knowledge_id))
            session.commit()


def select_index(knowledge_id):
    from sqlalchemy import select

    from app.models.index import IndexVersion

    return select(IndexVersion.id).where(IndexVersion.knowledge_set_id == knowledge_id)
