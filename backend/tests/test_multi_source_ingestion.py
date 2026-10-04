"""Several Website sources merged into one index (multi-source slice 1)."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion_content.cleaning import default_structure_steps
from app.models.document import Chunk
from app.models.index import IndexVersion
from app.models.ingestion import IngestionRun
from app.models.source import (
    IndexSourceRevision,
    SourceItem,
    SourceRevision,
    SourceSnapshotMember,
)
from test_ingestion_contracts import ingestion_draft
from test_documents import documents_api  # noqa: F401
from test_website_ingestion import page, publish, start_run, website_api  # noqa: F401

SITE_A = "https://example.com/0"
SITE_B = "https://example.com/1"


@pytest.fixture
def api(website_api):  # noqa: F811
    return website_api


class MultiSiteDouble:
    """Returns the pages of whichever source is being crawled, by its URL."""

    def __init__(self, pages_by_source_url):
        self.pages_by_source_url = pages_by_source_url
        self.crawled = []

    def crawl(self, config, policy, priors, store):
        url = str(config.selection.url)
        self.crawled.append(url)
        pages = self.pages_by_source_url[url]
        return store.import_results(
            [value[0] for value in pages], [value[1] for value in pages]
        )


def merged_draft(config, *, source_count=2, structure_cleaning=False):
    payload = ingestion_draft(source_count=source_count)
    for node in payload["execution"]["nodes"]:
        if node["type"] == "embed":
            node.update(
                provider=config.provider,
                model=config.model,
                dimensions=config.dimensions,
                config_version=config.revision,
            )
        elif node["type"] == "chunk":
            node.update(size=100, overlap=10)
    if structure_cleaning:
        payload["execution"]["schema_version"] = 2
        for node in payload["execution"]["nodes"]:
            if node["type"] == "extract":
                node.update(strategy="native_text", config_version="native-text-v1")
            elif node["type"] == "clean":
                node.update(
                    profile="structure-aware-v1",
                    config_version="structure-clean-v1",
                    steps=default_structure_steps(),
                )
            elif node["type"] == "chunk":
                node.update(config_version="character-window-v1")
    return payload


def save(client, project_id, payload):
    saved = client.post(f"/api/projects/{project_id}/pipelines", json=payload)
    assert saved.status_code == 201, saved.text
    return saved.json()


def html(title, text):
    return f"<main><h1>{title}</h1><p>{text}</p></main>".encode()


def memberships(engine, index_id):
    with Session(engine) as session:
        return session.execute(
            select(IndexSourceRevision.source_node_id, SourceItem.canonical_location)
            .join(SourceItem, SourceItem.id == IndexSourceRevision.source_item_id)
            .where(IndexSourceRevision.index_id == index_id)
        ).all()


def run_items(client, project_id, run_id):
    response = client.get(f"/api/projects/{project_id}/ingestion-runs/{run_id}/items")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def snapshot_provenance(engine, run_id):
    with Session(engine) as session:
        run = session.get(IngestionRun, UUID(run_id))
        rows = session.execute(
            select(SourceItem.canonical_location, SourceSnapshotMember.provenance)
            .join(SourceItem, SourceItem.id == SourceSnapshotMember.source_item_id)
            .where(SourceSnapshotMember.snapshot_id == run.source_snapshot_id)
        ).all()
    return dict(rows)


def test_two_websites_publish_one_index_with_each_sources_pages(api):
    client, engine, project_id, _, config, _ = api
    version = save(client, project_id, merged_draft(config))
    run = start_run(client, project_id, version)
    double = MultiSiteDouble(
        {
            SITE_A: [
                page(SITE_A, html("Orchard", "The orchard grows apples.")),
                page(f"{SITE_A}/harvest", html("Harvest", "Harvest is in September.")),
            ],
            SITE_B: [page(SITE_B, html("Greenhouse", "The greenhouse grows pears."))],
        }
    )
    index_id = publish(engine, run["id"], lambda: double)

    assert sorted(double.crawled) == [SITE_A, SITE_B]
    assert sorted(memberships(engine, index_id)) == [
        ("source-0", SITE_A),
        ("source-0", f"{SITE_A}/harvest"),
        ("source-1", SITE_B),
    ]
    result = client.get(f"/api/projects/{project_id}/ingestion-runs/{run['id']}")
    assert result.json()["status"] == "succeeded"
    assert result.json()["new_count"] == 3


def test_same_page_from_two_sources_is_indexed_once_with_both_provenances(api):
    client, engine, project_id, _, config, _ = api
    version = save(client, project_id, merged_draft(config))
    run = start_run(client, project_id, version)
    shared = "https://example.com/shared"
    shared_body = html("Shared", "Both sites link to this shipping policy.")
    double = MultiSiteDouble(
        {
            SITE_A: [
                page(SITE_A, html("Orchard", "The orchard grows apples.")),
                page(shared, shared_body),
            ],
            SITE_B: [
                page(SITE_B, html("Greenhouse", "The greenhouse grows pears.")),
                page(shared, shared_body),
            ],
        }
    )
    index_id = publish(engine, run["id"], lambda: double)

    assert sorted(memberships(engine, index_id)) == [
        ("source-0", SITE_A),
        ("source-0", shared),
        ("source-1", SITE_B),
    ]
    items = run_items(client, project_id, run["id"])
    duplicate = next(item for item in items if item["outcome"] == "duplicate")
    assert duplicate["source_node_id"] == "source-1"
    assert "indexed once" in duplicate["reason"]
    assert snapshot_provenance(engine, run["id"])[shared]["also_found"] == [
        {
            "source_node_id": "source-1",
            "canonical_location": shared,
            "reason": "same_page",
        }
    ]


def test_cross_site_duplicate_content_keeps_the_excluded_location(api):
    client, engine, project_id, _, config, _ = api
    version = save(client, project_id, merged_draft(config))
    run = start_run(client, project_id, version)
    mirrored = html("Returns", "Returns are accepted within thirty days of delivery.")
    double = MultiSiteDouble(
        {
            SITE_A: [page(SITE_A, mirrored)],
            SITE_B: [page(SITE_B, mirrored)],
        }
    )
    index_id = publish(engine, run["id"], lambda: double)

    assert memberships(engine, index_id) == [("source-0", SITE_A)]
    excluded = next(
        item
        for item in run_items(client, project_id, run["id"])
        if item["outcome"] == "excluded"
    )
    assert excluded["source_node_id"] == "source-1"
    assert snapshot_provenance(engine, run["id"])[SITE_A]["also_found"] == [
        {
            "source_node_id": "source-1",
            "canonical_location": SITE_B,
            "reason": "exact_cleaned_sha256",
        }
    ]


def test_repeated_chrome_is_measured_per_source(api):
    client, engine, project_id, _, config, _ = api
    version = save(client, project_id, merged_draft(config, structure_cleaning=True))
    run = start_run(client, project_id, version)
    notice = "Free shipping on every order over fifty dollars."

    def with_notice(title, text):
        return f"<main><h1>{title}</h1><p>{text}</p><p>{notice}</p></main>".encode()

    double = MultiSiteDouble(
        {
            # The notice repeats on every page of site A: it is site chrome there.
            SITE_A: [
                page(SITE_A, with_notice("Orchard", "Apples ripen in autumn.")),
                page(f"{SITE_A}/a", with_notice("Pruning", "Prune in late winter.")),
                page(f"{SITE_A}/b", with_notice("Soil", "Apples like loamy soil.")),
            ],
            # On site B it appears on one page of three: it is content there.
            SITE_B: [
                page(SITE_B, with_notice("Greenhouse", "Pears grow under glass.")),
                page(f"{SITE_B}/a", html("Watering", "Water pears weekly.")),
                page(f"{SITE_B}/b", html("Heating", "Keep the glasshouse warm.")),
            ],
        }
    )
    index_id = publish(engine, run["id"], lambda: double)

    with Session(engine) as session:
        index = session.get(IndexVersion, index_id)
        assert index.status == "succeeded"
        rows = session.execute(
            select(SourceItem.canonical_location, Chunk.text)
            .join(SourceRevision, SourceRevision.source_item_id == SourceItem.id)
            .join(Chunk, Chunk.run_id == SourceRevision.processing_run_id)
            .join(
                IndexSourceRevision,
                IndexSourceRevision.source_revision_id == SourceRevision.id,
            )
            .where(IndexSourceRevision.index_id == index_id)
        ).all()
    text_by_location = {}
    for location, text in rows:
        text_by_location[location] = text_by_location.get(location, "") + text
    assert notice not in text_by_location[SITE_A]
    assert notice in text_by_location[SITE_B]


def test_saving_more_than_five_websites_is_rejected(api):
    client, _, project_id, _, config, _ = api
    response = client.post(
        f"/api/projects/{project_id}/pipelines",
        json=merged_draft(config, source_count=6),
    )
    assert response.status_code == 422, response.text
    issue = response.json()["detail"][0]
    assert issue["loc"] == ["execution", "nodes"]
    assert "at most 5 Website sources" in issue["msg"]
    assert save(client, project_id, merged_draft(config, source_count=5))


def test_saving_mixed_connector_kinds_is_rejected(api):
    client, _, project_id, _, config, _ = api
    payload = merged_draft(config)
    payload["execution"]["nodes"][1]["config"] = {
        "kind": "existing_files",
        "document_ids": [str(uuid4())],
    }
    response = client.post(f"/api/projects/{project_id}/pipelines", json=payload)
    assert response.status_code == 422, response.text
    issue = response.json()["detail"][0]
    assert issue["loc"] == ["execution", "nodes", 1, "config", "kind"]
    assert "same connector" in issue["msg"]


def test_saving_websites_over_the_aggregate_page_cap_is_rejected(api):
    client, _, project_id, _, config, _ = api
    payload = merged_draft(config, source_count=3)
    for node in payload["execution"]["nodes"]:
        if node["type"] == "source":
            node["config"]["max_pages"] = 1000
    response = client.post(f"/api/projects/{project_id}/pipelines", json=payload)
    assert response.status_code == 422, response.text
    issues = response.json()["detail"]
    assert [issue["loc"][2] for issue in issues] == [0, 1, 2]
    assert all(issue["loc"][-2:] == ["website", "max_pages"] for issue in issues)
    assert "at most 2,500 pages; they now allow 3,000" in issues[0]["msg"]
    payload["execution"]["nodes"][2]["config"]["max_pages"] = 500
    assert save(client, project_id, payload)


def test_saved_v2_versions_record_the_merged_layout(api):
    client, _, project_id, _, config, _ = api
    payload = merged_draft(config, structure_cleaning=True)
    saved = save(client, project_id, payload)
    assert saved["execution"]["index_layout"] == "merged"
    payload["execution"]["index_layout"] = "per_source"
    rejected = client.post(f"/api/projects/{project_id}/pipelines", json=payload)
    assert rejected.status_code == 422, rejected.text
