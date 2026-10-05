"""One index per Website source: run groups (multi-source slice 5)."""

from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import ProcessingRun
from app.models.index import IndexVersion, KnowledgeSet
from app.models.ingestion import IngestionRun
from app.models.source import IndexSourceRevision, SourceItem, SourceRevision
from test_documents import documents_api  # noqa: F401
from test_ingestion_schedules import payload as schedule_payload
from test_multi_source_ingestion import (
    SITE_A,
    SITE_B,
    SITE_DOWN,
    MultiSiteDouble,
    html,
)
from test_website_ingestion import page, publish, website_api  # noqa: F401


@pytest.fixture
def api(website_api):  # noqa: F811
    return website_api


def per_source_draft(config, count=2):
    nodes, edges = [], []
    for number in range(count):
        chain = [
            {
                "id": f"source-{number}",
                "type": "source",
                "config": {
                    "kind": "website",
                    "selection": {
                        "mode": "single_url",
                        "url": f"https://example.com/{number}",
                    },
                    "allowed_origins": ["https://example.com"],
                    "max_pages": 10,
                    "max_depth": 2,
                    "requests_per_second": 2,
                },
            },
            {
                "id": f"extract-{number}",
                "type": "extract",
                "strategy": "native_text",
                "config_version": "native-text-v1",
            },
            {
                "id": f"clean-{number}",
                "type": "clean",
                "normalize_whitespace": True,
                "repeated_boilerplate": [],
                "profile": "standard-v1",
                "config_version": "deterministic-clean-v1",
            },
            {
                "id": f"chunk-{number}",
                "type": "chunk",
                # Each branch keeps its own settings.
                "size": 100 + number * 100,
                "overlap": 10,
                "config_version": "character-window-v1",
            },
            {
                "id": f"embed-{number}",
                "type": "embed",
                "provider": config.provider,
                "model": config.model,
                "dimensions": config.dimensions,
                "config_version": config.revision,
            },
            {
                "id": f"publish-{number}",
                "type": "publish_index",
                "knowledge_set_name": f"Docs · site {number}",
            },
        ]
        nodes += chain
        edges += [
            {"source": left["id"], "target": right["id"]}
            for left, right in zip(chain, chain[1:])
        ]
    return {
        "kind": "ingestion",
        "name": "Per-source docs",
        "execution": {
            "schema_version": 2,
            "index_layout": "per_source",
            "nodes": nodes,
            "edges": edges,
        },
        "layout": {
            "positions": {
                node["id"]: {"x": index * 10, "y": 0}
                for index, node in enumerate(nodes)
            }
        },
    }


def save(client, project_id, draft):
    response = client.post(f"/api/projects/{project_id}/pipelines", json=draft)
    assert response.status_code == 201, response.text
    return response.json()


def group_route(project_id, version):
    return (
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}"
        f"/versions/{version['id']}/ingestion-run-groups"
    )


def start_group(client, project_id, version, body=None):
    response = client.post(group_route(project_id, version), json=body)
    assert response.status_code == 202, response.text
    return response.json()


def read_group(client, project_id, group_id):
    response = client.get(f"/api/projects/{project_id}/ingestion-run-groups/{group_id}")
    assert response.status_code == 200, response.text
    return response.json()


def two_sites():
    return {
        SITE_A: [page(SITE_A, html("Orchard", "The orchard grows apples."))],
        SITE_B: [page(SITE_B, html("Greenhouse", "The greenhouse grows pears."))],
    }


def test_per_source_layout_validation(api):
    client, _, project_id, _, config, _ = api
    saved = save(client, project_id, per_source_draft(config))
    assert saved["execution"]["index_layout"] == "per_source"

    shared = per_source_draft(config)
    edges = shared["execution"]["edges"]
    edges[0] = {"source": "source-0", "target": "extract-1"}
    response = client.post(f"/api/projects/{project_id}/pipelines", json=shared)
    assert response.status_code == 422, response.text
    assert "its own" in response.text

    same_name = per_source_draft(config)
    for node in same_name["execution"]["nodes"]:
        if node["type"] == "publish_index":
            node["knowledge_set_name"] = "Docs"
    response = client.post(f"/api/projects/{project_id}/pipelines", json=same_name)
    assert response.status_code == 422, response.text
    assert "differently named index" in response.text

    preview = client.post(
        f"/api/projects/{project_id}/ingestion-previews",
        json={"execution": per_source_draft(config)["execution"]},
    )
    assert preview.status_code == 422, preview.text

    single = client.post(
        f"/api/projects/{project_id}/pipelines/{saved['pipeline_id']}"
        f"/versions/{saved['id']}/ingestion-runs",
        json={},
    )
    assert single.status_code == 409, single.text
    assert "run group" in single.json()["detail"]


def test_a_group_publishes_one_index_per_source_with_its_own_settings(api):
    client, engine, project_id, _, config, _ = api
    version = save(client, project_id, per_source_draft(config))
    group = start_group(client, project_id, version)
    assert group["status"] == "queued"
    assert [run["branch_source_node_id"] for run in group["runs"]] == [
        "source-0",
        "source-1",
    ]
    for run in group["runs"]:
        publish(engine, run["id"], lambda: MultiSiteDouble(two_sites()))

    finished = read_group(client, project_id, group["id"])
    assert finished["status"] == "succeeded"
    assert finished["completion"] == "complete"
    with Session(engine) as session:
        rows = session.execute(
            select(
                KnowledgeSet.name,
                SourceItem.canonical_location,
                ProcessingRun.chunk_size,
            )
            .select_from(IndexSourceRevision)
            .join(IndexVersion, IndexVersion.id == IndexSourceRevision.index_id)
            .join(KnowledgeSet, KnowledgeSet.id == IndexVersion.knowledge_set_id)
            .join(SourceItem, SourceItem.id == IndexSourceRevision.source_item_id)
            .join(
                SourceRevision,
                SourceRevision.id == IndexSourceRevision.source_revision_id,
            )
            .join(ProcessingRun, ProcessingRun.id == SourceRevision.processing_run_id)
            .where(IndexVersion.project_id == UUID(project_id))
        ).all()
    assert sorted(rows) == [
        ("Docs · site 0", SITE_A, 100),
        ("Docs · site 1", SITE_B, 200),
    ]
    listed = client.get(
        f"/api/projects/{project_id}/ingestion-run-groups",
        params={"pipeline_version_id": version["id"]},
    ).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == group["id"]


def test_one_failed_branch_does_not_stop_the_others(api):
    client, engine, project_id, _, config, _ = api
    version = save(client, project_id, per_source_draft(config))
    group = start_group(client, project_id, version)
    pages = two_sites()
    pages[SITE_A] = SITE_DOWN
    from app.workers.ingestion import process_ingestion

    failing, working = group["runs"]
    process_ingestion(
        UUID(failing["id"]), engine, connector_factory=lambda: MultiSiteDouble(pages)
    )
    publish(engine, working["id"], lambda: MultiSiteDouble(pages))

    finished = read_group(client, project_id, group["id"])
    assert finished["status"] == "partial"
    statuses = {run["branch_source_node_id"]: run["status"] for run in finished["runs"]}
    assert statuses == {"source-0": "failed", "source-1": "succeeded"}
    published = next(run for run in finished["runs"] if run["status"] == "succeeded")
    assert published["published_index_id"]


def test_a_busy_branch_blocks_the_whole_group_start(api):
    client, engine, project_id, _, config, _ = api
    version = save(client, project_id, per_source_draft(config))
    start_group(client, project_id, version, {"source_node_ids": ["source-1"]})
    with Session(engine) as session:
        before = session.scalar(select(func.count()).select_from(IngestionRun))

    busy = client.post(group_route(project_id, version), json={})
    assert busy.status_code == 409, busy.text
    assert "Docs · site 1" in busy.json()["detail"]
    assert "no branch was started" in busy.json()["detail"]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(IngestionRun)) == before


def test_a_group_can_start_selected_branches_and_be_cancelled(api):
    client, _, project_id, _, config, _ = api
    version = save(client, project_id, per_source_draft(config))
    only = start_group(client, project_id, version, {"source_node_ids": ["source-1"]})
    assert [run["branch_source_node_id"] for run in only["runs"]] == ["source-1"]
    cancelled = client.post(
        f"/api/projects/{project_id}/ingestion-run-groups/{only['id']}/cancel"
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"

    unknown = client.post(
        group_route(project_id, version), json={"source_node_ids": ["source-9"]}
    )
    assert unknown.status_code == 422, unknown.text


def test_a_schedule_starts_a_group_for_a_per_source_version(api):
    client, engine, project_id, _, config, _ = api
    version = save(client, project_id, per_source_draft(config))
    route = f"/api/projects/{project_id}/ingestion-schedules"
    schedule = client.post(route, json=schedule_payload(version)).json()
    run = client.post(f"{route}/{schedule['id']}/run")
    assert run.status_code == 202, run.text
    assert run.json()["group_id"]
    group = read_group(client, project_id, run.json()["group_id"])
    assert group["trigger_kind"] == "scheduled"
    assert len(group["runs"]) == 2


def test_merged_versions_cannot_start_groups(api):
    client, _, project_id, _, config, _ = api
    draft = per_source_draft(config, count=1)
    draft["execution"]["index_layout"] = "merged"
    version = save(client, project_id, draft)
    response = client.post(group_route(project_id, version), json={})
    assert response.status_code == 409, response.text
