from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors.s3 import S3Connector
from app.core.config import settings
from app.models.index import IndexVersion, KnowledgeSet
from app.models.ingestion import IngestionRun
from app.models.pipeline import PipelineVersion
from app.models.source import IndexSourceRevision, SourceItem, SourceRevision
from app.services import ingestion
from app.workers.dispatcher import dispatch_ingestion_once
from app.workers.ingestion import process_ingestion
from app.workers.processing import now
from test_connections import KEY_1, encoded
from test_documents import documents_api, pdf_bytes  # noqa: F401
from test_ingestion_contracts import ingestion_draft
from test_website_ingestion import publish, start_run, website_api  # noqa: F401


NOW = datetime(2026, 9, 13, tzinfo=UTC)


class Body:
    def __init__(self, value):
        self.value = value

    def read(self, limit):
        return self.value[:limit]

    def close(self):
        pass


class BucketDouble:
    def __init__(self, objects):
        self.objects = objects
        self.gets = []
        self.denied = False

    def list_objects_v2(self, **kwargs):
        if self.denied:
            from botocore.exceptions import ClientError

            raise ClientError(
                {
                    "Error": {
                        "Code": "AccessDenied",
                        "Message": "unsafe provider body",
                    },
                    "ResponseMetadata": {"HTTPStatusCode": 403},
                },
                "ListObjectsV2",
            )
        prefix = kwargs.get("Prefix", "")
        return {
            "Contents": [
                {
                    "Key": key,
                    "Size": len(value[0]),
                    "ETag": f'"{value[1]}"',
                    "LastModified": NOW,
                }
                for key, value in sorted(self.objects.items())
                if key.startswith(prefix)
            ],
            "IsTruncated": False,
        }

    def head_object(self, **kwargs):
        value = self.objects[kwargs["Key"]]
        return {
            "ContentLength": len(value[0]),
            "ETag": f'"{value[1]}"',
            "LastModified": NOW,
            "VersionId": value[2],
        }

    def get_object(self, **kwargs):
        key = kwargs["Key"]
        value = self.objects[key]
        self.gets.append(key)
        assert kwargs.get("VersionId") == value[2]
        return {"Body": Body(value[0]), **self.head_object(Key=key)}


def save_s3(client, project_id, embedding, connection_id):
    payload = ingestion_draft()
    payload["name"] = "S3 ingestion"
    payload["execution"]["nodes"][0]["config"] = {
        "kind": "s3",
        "connection_id": connection_id,
        "region": "us-east-1",
        "bucket": "research-archive",
        "prefix": "docs/",
        "expected_bucket_owner": "123456789012",
        "allowed_file_types": ["txt", "pdf"],
        "max_objects": 100,
        "max_pages": 2,
        "max_object_bytes": 10000,
        "max_total_bytes": 50000,
        "request_timeout_seconds": 5,
    }
    embed = next(
        node for node in payload["execution"]["nodes"] if node["type"] == "embed"
    )
    embed.update(
        provider=embedding.provider,
        model=embedding.model,
        dimensions=embedding.dimensions,
        config_version=embedding.revision,
    )
    chunk = next(
        node for node in payload["execution"]["nodes"] if node["type"] == "chunk"
    )
    chunk.update(size=100, overlap=10)
    response = client.post(f"/api/projects/{project_id}/pipelines", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def connector_factory(bucket):
    return lambda credentials: S3Connector(
        credentials, client_factory=lambda credentials, region, timeout: bucket
    )


def test_s3_first_run_incremental_refresh_and_safe_permission_loss(
    website_api,  # noqa: F811
    monkeypatch,
):
    client, engine, project_id, _, embedding, provider = website_api
    monkeypatch.setattr(settings, "source_connections_enabled", True)
    monkeypatch.setattr(settings, "source_connection_active_key", "v1")
    monkeypatch.setattr(settings, "source_connection_keys", {"v1": encoded(KEY_1)})
    connection = client.post(
        f"/api/projects/{project_id}/source-connections",
        json={
            "name": "Research bucket",
            "credentials": {
                "kind": "s3",
                "access_key_id": "fixture-access",
                "secret_access_key": "fixture-secret",
            },
        },
    ).json()
    version = save_s3(client, project_id, embedding, connection["id"])
    public_start = client.post(
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}"
        f"/versions/{version['id']}/ingestion-runs",
        headers={"host": "public.example"},
    )
    assert public_start.status_code == 403
    with Session(engine) as session:
        saved = session.get(PipelineVersion, UUID(version["id"]))
        assert "fixture-secret" not in str(saved.execution)
        assert "fixture-access" not in str(saved.execution)
    stable = b"The orchard grows apples in carefully managed research rows. " * 3
    changed = b"The harvest manual starts in September and covers storage. " * 3
    removed = b"This historical object will be removed from the next listing. " * 3
    pdf = pdf_bytes(
        [
            "PDF guidance says orchard teams inspect ladders before every harvest shift. "
            * 2
        ]
    )
    bucket = BucketDouble(
        {
            "docs/orchard.txt": (stable, "orchard-v1", "version-orchard-1"),
            "docs/manual.txt": (changed, "manual-v1", "version-manual-1"),
            "docs/old.txt": (removed, "old-v1", "version-old-1"),
            "docs/safety.pdf": (pdf, "safety-v1", "version-safety-1"),
        }
    )
    first = start_run(client, project_id, version)
    first_index = publish(engine, first["id"], connector_factory(bucket))
    assert set(bucket.gets) == set(bucket.objects)
    first_calls = len(provider.calls)

    bucket.gets.clear()
    bucket.objects = {
        "docs/orchard.txt": (stable, "orchard-v1", "version-orchard-1"),
        "docs/manual.txt": (
            b"The harvest manual now starts in October and covers cold storage. " * 3,
            "manual-v2",
            "version-manual-2",
        ),
        "docs/new.txt": (
            b"New packing guidance requires recycled paper boxes for apples. " * 3,
            "new-v1",
            "version-new-1",
        ),
        "docs/safety.pdf": (pdf, "safety-v1", "version-safety-1"),
    }
    second = start_run(client, project_id, version)
    second_index = publish(engine, second["id"], connector_factory(bucket))
    assert set(bucket.gets) == {"docs/manual.txt", "docs/new.txt"}
    assert all(
        "orchard grows apples" not in text
        for call in provider.calls[first_calls:]
        for text in call
    )
    result = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{second['id']}"
    ).json()
    assert (result["new_count"], result["changed_count"]) == (1, 1)
    assert (result["unchanged_count"], result["removed_count"]) == (2, 1)
    items = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{second['id']}/items"
    ).json()["items"]
    assert all(item["source_kind"] == "s3" for item in items)
    assert {item["outcome"] for item in items} == {
        "new",
        "changed",
        "unchanged",
        "removed",
    }
    with Session(engine) as session:
        indexes = session.scalars(
            select(IndexVersion)
            .where(IndexVersion.id.in_([first_index, second_index]))
            .order_by(IndexVersion.version)
        ).all()
        assert [index.status for index in indexes] == ["succeeded", "succeeded"]
        assert session.scalar(select(func.count()).select_from(SourceRevision)) == 6
        assert (
            session.scalar(
                select(func.count())
                .select_from(IndexSourceRevision)
                .where(IndexSourceRevision.index_id == second_index)
            )
            == 4
        )
        revisions = session.scalars(
            select(SourceRevision).join(SourceItem).where(SourceItem.kind == "s3")
        ).all()
        assert all(
            item.provenance["connection_id"] == connection["id"] for item in revisions
        )
        assert all(
            item.provenance["bucket"] == "research-archive" for item in revisions
        )

    retrieval = client.post(
        f"/api/projects/{project_id}/retrieval",
        json={"index_id": str(second_index), "query": "paper boxes", "top_k": 20},
    )
    assert retrieval.status_code == 200
    assert any(
        item["source_url"] == "s3://research-archive/docs/new.txt"
        for item in retrieval.json()["items"]
    ), retrieval.json()

    snapshot_id = result["source_snapshot_id"]
    assert snapshot_id is not None
    offline = start_run(
        client,
        project_id,
        version,
        source_input={"kind": "snapshot", "source_snapshot_id": snapshot_id},
        destination={"kind": "new", "name": "Offline S3 variant"},
    )

    def unexpected_connector(_credentials):
        raise AssertionError("Stored S3 reprocessing must not call the provider.")

    offline_index = publish(engine, offline["id"], unexpected_connector)
    offline_result = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{offline['id']}"
    ).json()
    assert offline_result["status"] == "succeeded"
    assert offline_result["source_snapshot_id"] == snapshot_id
    assert offline_result["knowledge_set_name"] == "Offline S3 variant"
    assert offline_index not in (first_index, second_index)

    bucket.denied = True
    failed = start_run(client, project_id, version)
    process_ingestion(
        UUID(failed["id"]), engine, connector_factory=connector_factory(bucket)
    )
    failed_result = client.get(
        f"/api/projects/{project_id}/ingestion-runs/{failed['id']}"
    ).json()
    assert failed_result["status"] == "failed"
    assert (
        failed_result["error"]
        == "Amazon S3 denied permission to list the selected bucket."
    )
    assert "unsafe provider body" not in failed_result["error"]
    with Session(engine) as session:
        run = session.get(IngestionRun, UUID(failed["id"]))
        assert (
            session.get(KnowledgeSet, run.knowledge_set_id).current_ready_index_id
            == second_index
        )


def test_s3_pipeline_rejects_cross_project_or_wrong_kind_connections(
    website_api,  # noqa: F811
    monkeypatch,
):
    client, _, project_id, other_project_id, embedding, _ = website_api
    monkeypatch.setattr(settings, "source_connections_enabled", True)
    monkeypatch.setattr(settings, "source_connection_active_key", "v1")
    monkeypatch.setattr(settings, "source_connection_keys", {"v1": encoded(KEY_1)})
    other = client.post(
        f"/api/projects/{other_project_id}/source-connections",
        json={
            "name": "Other project bucket",
            "credentials": {
                "kind": "s3",
                "access_key_id": "other-access",
                "secret_access_key": "other-secret",
            },
        },
    ).json()
    payload = ingestion_draft()
    payload["execution"]["nodes"][0]["config"] = {
        "kind": "s3",
        "connection_id": other["id"],
        "region": "us-east-1",
        "bucket": "other-project-bucket",
        "allowed_file_types": ["txt"],
        "max_objects": 10,
        "max_pages": 1,
        "max_object_bytes": 1024,
        "max_total_bytes": 2048,
        "request_timeout_seconds": 5,
    }
    embed = next(
        node for node in payload["execution"]["nodes"] if node["type"] == "embed"
    )
    embed.update(
        provider=embedding.provider,
        model=embedding.model,
        dimensions=embedding.dimensions,
        config_version=embedding.revision,
    )
    rejected = client.post(f"/api/projects/{project_id}/pipelines", json=payload)
    assert rejected.status_code == 404

    notion = client.post(
        f"/api/projects/{project_id}/source-connections",
        json={
            "name": "Wrong kind",
            "credentials": {"kind": "notion", "integration_token": "notion-token"},
        },
    ).json()
    payload["execution"]["nodes"][0]["config"]["connection_id"] = notion["id"]
    wrong = client.post(f"/api/projects/{project_id}/pipelines", json=payload)
    assert wrong.status_code == 404


def test_s3_cancellation_duplicate_delivery_and_stale_recovery(
    website_api,  # noqa: F811
    monkeypatch,
):
    client, engine, project_id, _, embedding, _ = website_api
    monkeypatch.setattr(settings, "source_connections_enabled", True)
    monkeypatch.setattr(settings, "source_connection_active_key", "v1")
    monkeypatch.setattr(settings, "source_connection_keys", {"v1": encoded(KEY_1)})
    connection = client.post(
        f"/api/projects/{project_id}/source-connections",
        json={
            "name": "Fenced bucket",
            "credentials": {
                "kind": "s3",
                "access_key_id": "fixture-access",
                "secret_access_key": "fixture-secret",
            },
        },
    ).json()
    version = save_s3(client, project_id, embedding, connection["id"])
    content = b"This content must only be published once after a durable run. " * 3
    bucket = BucketDouble({"docs/only.txt": (content, "only-v1", "version-only-1")})

    completed = start_run(client, project_id, version)
    publish(engine, completed["id"], connector_factory(bucket))
    calls_after_success = list(bucket.gets)
    process_ingestion(
        UUID(completed["id"]), engine, connector_factory=connector_factory(bucket)
    )
    assert bucket.gets == calls_after_success
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(SourceRevision)) == 1

    cancelled = start_run(client, project_id, version)

    class CancellingConnector(S3Connector):
        def fetch_all(self, config, priors, processing_config_hash):
            outcomes = super().fetch_all(config, priors, processing_config_hash)
            with Session(engine) as session:
                ingestion.cancel_run(session, UUID(project_id), UUID(cancelled["id"]))
            return outcomes

    process_ingestion(
        UUID(cancelled["id"]),
        engine,
        connector_factory=lambda credentials: CancellingConnector(
            credentials,
            client_factory=lambda credentials, region, timeout: bucket,
        ),
    )
    with Session(engine) as session:
        assert session.get(IngestionRun, UUID(cancelled["id"])).status == "cancelled"
        assert session.scalar(select(func.count()).select_from(SourceRevision)) == 1

    stale = start_run(client, project_id, version)
    stale_id = UUID(stale["id"])
    with Session(engine) as session:
        job = session.get(IngestionRun, stale_id)
        job.status = "running"
        job.started_at = now() - timedelta(seconds=3661)
        session.commit()
    sent = []
    dispatch_ingestion_once(engine, send=lambda value: sent.append(value))
    with Session(engine) as session:
        assert session.get(IngestionRun, stale_id).status == "queued"
