"""Several Website sources merged into one index (multi-source slice 1)."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import ConnectorFailure, ConnectorIssue
from app.connectors.website import PreviewOutcome
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
from app.workers.ingestion import process_ingestion
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
        if isinstance(pages, ConnectorIssue):
            raise ConnectorFailure(pages)
        return store.import_results(
            [value[0] for value in pages], [value[1] for value in pages if value[1]]
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


# Slice 2: one failing site does not block the others in a merged run.

SITE_DOWN = ConnectorIssue(
    code="sitemap_unavailable",
    message="The sitemap could not be read.",
    retryable=False,
)


def failed_page(url):
    return (
        PreviewOutcome(
            external_id=url,
            display_name=url,
            canonical_location=url,
            media_type="text/html",
            status="failed",
            reason="The page returned HTTP 500.",
            error_code="http_500",
        ),
        None,
    )


def two_site_pages(b_text="The greenhouse grows pears."):
    return {
        SITE_A: [page(SITE_A, html("Orchard", "The orchard grows apples."))],
        SITE_B: [
            page(SITE_B, html("Greenhouse", b_text)),
            page(f"{SITE_B}/glass", html("Glass", "Panes are cleaned in spring.")),
        ],
    }


def read_run(client, project_id, run_id):
    response = client.get(f"/api/projects/{project_id}/ingestion-runs/{run_id}")
    assert response.status_code == 200, response.text
    return response.json()


def outcome_for(run, node_id):
    return next(
        item for item in run["source_outcomes"] if item["source_node_id"] == node_id
    )


def test_first_run_publishes_the_working_site_when_another_fails(api):
    client, engine, project_id, _, config, _ = api
    version = save(client, project_id, merged_draft(config))
    run = start_run(client, project_id, version)
    pages = two_site_pages()
    pages[SITE_B] = SITE_DOWN
    index_id = publish(engine, run["id"], lambda: MultiSiteDouble(pages))

    assert memberships(engine, index_id) == [("source-0", SITE_A)]
    result = read_run(client, project_id, run["id"])
    assert result["status"] == "succeeded"
    assert result["completion"] == "with_warnings"
    failed = outcome_for(result, "source-1")
    assert failed["status"] == "failed"
    assert failed["error_code"] == "sitemap_unavailable"
    assert failed["message"] == "The sitemap could not be read."
    assert failed["carried_forward_count"] == 0
    assert outcome_for(result, "source-0")["status"] == "succeeded"


def test_a_failed_site_keeps_its_last_good_pages(api):
    client, engine, project_id, _, config, _ = api
    version = save(client, project_id, merged_draft(config))
    first = start_run(client, project_id, version)
    publish(engine, first["id"], lambda: MultiSiteDouble(two_site_pages()))
    assert read_run(client, project_id, first["id"])["completion"] == "complete"

    second = start_run(client, project_id, version)
    pages = two_site_pages()
    pages[SITE_A] = [page(SITE_A, html("Orchard", "Now with plums as well."))]
    pages[SITE_B] = SITE_DOWN
    index_id = publish(engine, second["id"], lambda: MultiSiteDouble(pages))

    assert sorted(memberships(engine, index_id)) == [
        ("source-0", SITE_A),
        ("source-1", SITE_B),
        ("source-1", f"{SITE_B}/glass"),
    ]
    items = run_items(client, project_id, second["id"])
    carried = [item for item in items if item["outcome"] == "carried_forward"]
    assert sorted(item["canonical_location"] for item in carried) == [
        SITE_B,
        f"{SITE_B}/glass",
    ]
    assert "this source failed: The sitemap could not be read." in carried[0]["reason"]
    assert not [item for item in items if item["outcome"] == "removed"]
    result = read_run(client, project_id, second["id"])
    assert result["completion"] == "with_warnings"
    assert result["changed_count"] == 1
    assert outcome_for(result, "source-1")["carried_forward_count"] == 2
    snapshot = client.get(
        f"/api/projects/{project_id}/source-snapshots/{result['source_snapshot_id']}"
    ).json()
    assert snapshot["carried_forward_count"] == 2


def test_every_site_failing_fails_the_run_and_keeps_the_ready_index(api):
    client, engine, project_id, _, config, _ = api
    version = save(client, project_id, merged_draft(config))
    first = start_run(client, project_id, version)
    first_index = publish(
        engine, first["id"], lambda: MultiSiteDouble(two_site_pages())
    )

    second = start_run(client, project_id, version)
    down = {SITE_A: SITE_DOWN, SITE_B: [failed_page(SITE_B)]}
    process_ingestion(
        UUID(second["id"]), engine, connector_factory=lambda: MultiSiteDouble(down)
    )
    result = read_run(client, project_id, second["id"])
    assert result["status"] == "failed"
    assert result["error"].startswith("Every Website source failed.")
    assert outcome_for(result, "source-1")["error_code"] == "all_pages_failed"
    with Session(engine) as session:
        assert (
            session.scalar(
                select(IndexVersion.id).where(
                    IndexVersion.ingestion_run_id == UUID(second["id"])
                )
            )
            is None
        )
        assert session.get(IndexVersion, first_index).status == "succeeded"


def test_a_failed_page_keeps_its_previous_copy_and_new_failures_are_reported(api):
    client, engine, project_id, _, config, _ = api
    version = save(client, project_id, merged_draft(config))
    first = start_run(client, project_id, version)
    publish(engine, first["id"], lambda: MultiSiteDouble(two_site_pages()))

    second = start_run(client, project_id, version)
    pages = two_site_pages()
    pages[SITE_B] = [
        page(SITE_B, html("Greenhouse", "The greenhouse grows pears.")),
        failed_page(f"{SITE_B}/glass"),
        failed_page(f"{SITE_B}/new"),
    ]
    index_id = publish(engine, second["id"], lambda: MultiSiteDouble(pages))

    assert sorted(memberships(engine, index_id)) == [
        ("source-0", SITE_A),
        ("source-1", SITE_B),
        ("source-1", f"{SITE_B}/glass"),
    ]
    items = run_items(client, project_id, second["id"])
    outcomes = {item["canonical_location"]: item["outcome"] for item in items}
    assert outcomes[f"{SITE_B}/new"] == "failed"
    result = read_run(client, project_id, second["id"])
    assert result["status"] == "succeeded"
    assert result["completion"] == "with_warnings"
    assert result["failed_count"] == 2
    partial = outcome_for(result, "source-1")
    assert partial["status"] == "partial"
    assert partial["carried_forward_count"] == 1


def test_carried_pages_are_reprocessed_when_settings_changed(api):
    client, engine, project_id, _, config, _ = api
    version = save(client, project_id, merged_draft(config))
    first = start_run(client, project_id, version)
    long_text = "Greenhouse panes are cleaned every spring by the team. " * 12
    publish(
        engine,
        first["id"],
        lambda: MultiSiteDouble(two_site_pages(b_text=long_text)),
    )
    with Session(engine) as session:
        before = session.execute(
            select(SourceRevision.id, SourceRevision.processing_config_hash)
            .join(SourceItem, SourceItem.id == SourceRevision.source_item_id)
            .where(SourceItem.canonical_location == SITE_B)
        ).one()

    changed = {
        "kind": "ingestion",
        "name": version["name"],
        "execution": version["execution"],
        "layout": version["layout"],
    }
    chunk = next(
        node for node in changed["execution"]["nodes"] if node["type"] == "chunk"
    )
    chunk.update(size=240, overlap=40)
    saved = client.post(
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}/versions",
        json=changed,
    )
    assert saved.status_code == 201, saved.text
    second = start_run(client, project_id, saved.json())
    pages = two_site_pages()
    pages[SITE_B] = SITE_DOWN
    index_id = publish(engine, second["id"], lambda: MultiSiteDouble(pages))

    with Session(engine) as session:
        revision_id, config_hash = session.execute(
            select(SourceRevision.id, SourceRevision.processing_config_hash)
            .join(
                IndexSourceRevision,
                IndexSourceRevision.source_revision_id == SourceRevision.id,
            )
            .join(SourceItem, SourceItem.id == SourceRevision.source_item_id)
            .where(
                IndexSourceRevision.index_id == index_id,
                SourceItem.canonical_location == SITE_B,
            )
        ).one()
    assert revision_id != before.id
    assert config_hash != before.processing_config_hash
    carried = next(
        item
        for item in run_items(client, project_id, second["id"])
        if item["canonical_location"] == SITE_B
    )
    assert carried["outcome"] == "carried_forward"
    assert carried["reason"].endswith("Reprocessed with this run's settings.")


def test_a_single_website_still_fails_on_a_failed_page(api):
    client, engine, project_id, _, config, _ = api
    version = save(client, project_id, merged_draft(config, source_count=1))
    run = start_run(client, project_id, version)
    pages = {
        SITE_A: [page(SITE_A, html("Orchard", "Apples.")), failed_page(f"{SITE_A}/x")]
    }
    process_ingestion(
        UUID(run["id"]), engine, connector_factory=lambda: MultiSiteDouble(pages)
    )
    result = read_run(client, project_id, run["id"])
    assert result["status"] == "failed"
    assert result["source_outcomes"] == []


# Slice 4: refresh one source and keep the others without contacting them.


def start_status(client, project_id, version, body):
    return client.post(
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}"
        f"/versions/{version['id']}/ingestion-runs",
        json=body,
    )


def test_refreshing_one_source_keeps_the_others_without_requests(api):
    client, engine, project_id, _, config, _ = api
    version = save(client, project_id, merged_draft(config))
    first = start_run(client, project_id, version)
    publish(engine, first["id"], lambda: MultiSiteDouble(two_site_pages()))

    refresh = start_run(
        client,
        project_id,
        version,
        source_input={"kind": "refresh", "source_node_ids": ["source-1"]},
    )
    pages = two_site_pages(b_text="The greenhouse now grows figs.")
    # Site A would fail if contacted; a refresh of source-1 must not reach it.
    pages[SITE_A] = SITE_DOWN
    double = MultiSiteDouble(pages)
    index_id = publish(engine, refresh["id"], lambda: double)

    assert double.crawled == [SITE_B]
    assert sorted(memberships(engine, index_id)) == [
        ("source-0", SITE_A),
        ("source-1", SITE_B),
        ("source-1", f"{SITE_B}/glass"),
    ]
    kept = next(
        item
        for item in run_items(client, project_id, refresh["id"])
        if item["canonical_location"] == SITE_A
    )
    assert kept["outcome"] == "carried_forward"
    assert "not refreshed in this run" in kept["reason"]
    result = read_run(client, project_id, refresh["id"])
    assert result["status"] == "succeeded"
    assert result["completion"] == "complete"
    assert result["changed_count"] == 1
    assert outcome_for(result, "source-0")["status"] == "skipped"
    assert outcome_for(result, "source-1")["status"] == "succeeded"


def test_refreshing_one_source_needs_a_ready_index_and_known_sources(api):
    client, engine, project_id, _, config, _ = api
    version = save(client, project_id, merged_draft(config))
    body = {"source_input": {"kind": "refresh", "source_node_ids": ["source-1"]}}
    early = start_status(client, project_id, version, body)
    assert early.status_code == 409, early.text
    assert "Run every source once" in early.json()["detail"]

    first = start_run(client, project_id, version)
    publish(engine, first["id"], lambda: MultiSiteDouble(two_site_pages()))
    unknown = start_status(
        client,
        project_id,
        version,
        {"source_input": {"kind": "refresh", "source_node_ids": ["source-9"]}},
    )
    assert unknown.status_code == 422, unknown.text
    assert "source-9" in unknown.json()["detail"]

    single = save(client, project_id, merged_draft(config, source_count=1))
    one = start_status(
        client,
        project_id,
        single,
        {"source_input": {"kind": "refresh", "source_node_ids": ["source-0"]}},
    )
    assert one.status_code == 422, one.text


def test_selecting_every_source_is_a_full_refresh(api):
    client, engine, project_id, _, config, _ = api
    version = save(client, project_id, merged_draft(config))
    first = start_run(client, project_id, version)
    publish(engine, first["id"], lambda: MultiSiteDouble(two_site_pages()))
    run = start_run(
        client,
        project_id,
        version,
        source_input={"kind": "refresh", "source_node_ids": ["source-1", "source-0"]},
    )
    double = MultiSiteDouble(two_site_pages())
    publish(engine, run["id"], lambda: double)
    assert sorted(double.crawled) == [SITE_A, SITE_B]
    with Session(engine) as session:
        recorded = session.get(IngestionRun, UUID(run["id"])).snapshot["source_input"]
    assert recorded == {"kind": "refresh"}
