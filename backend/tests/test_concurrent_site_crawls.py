"""Website sources in one run crawl at the same time (multi-source slice 6)."""

import threading
from types import SimpleNamespace

import pytest
from sqlalchemy import event

from app.connectors.base import ConnectorIssue
from app.core.config import settings
from app.workers.remote_ingestion import _origin_lanes, _StoppableStore
from test_multi_source_ingestion import (
    MultiSiteDouble,
    html,
    memberships,
    merged_draft,
    save,
)
from test_documents import documents_api  # noqa: F401
from test_website_ingestion import page, publish, start_run, website_api  # noqa: F401


@pytest.fixture
def api(website_api):  # noqa: F811
    return website_api


def sites_draft(config, origins):
    """A merged draft whose sources each crawl a different site."""
    payload = merged_draft(config, source_count=len(origins))
    sources = [
        node for node in payload["execution"]["nodes"] if node["type"] == "source"
    ]
    for node, origin in zip(sources, origins):
        node["config"]["selection"]["url"] = f"{origin}/"
        node["config"]["allowed_origins"] = [origin]
    return payload


class ConcurrentDouble(MultiSiteDouble):
    """Records how many sources crawl at once, optionally waiting at a barrier."""

    def __init__(self, pages_by_source_url, barrier=None, hold=0.0):
        super().__init__(pages_by_source_url)
        self.barrier = barrier
        self.hold = hold
        self.lock = threading.Lock()
        self.active = 0
        self.peak = 0

    def crawl(self, config, policy, priors, store):
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            if self.barrier is not None:
                # Times out, and fails the test, if the sources crawl in turn.
                self.barrier.wait(timeout=10)
            if self.hold:
                threading.Event().wait(self.hold)
            return super().crawl(config, policy, priors, store)
        finally:
            with self.lock:
                self.active -= 1


def site_pages(origins):
    return {
        f"{origin}/": [page(f"{origin}/", html(origin, f"Pages served by {origin}."))]
        for origin in origins
    }


def test_sources_on_different_sites_crawl_at_the_same_time(api):
    client, engine, project_id, _, config, _ = api
    origins = ["https://orchard.example", "https://greenhouse.example"]
    version = save(client, project_id, sites_draft(config, origins))
    run = start_run(client, project_id, version)
    double = ConcurrentDouble(site_pages(origins), barrier=threading.Barrier(2))

    index_id = publish(engine, run["id"], lambda: double)

    assert double.peak == 2
    assert sorted(memberships(engine, index_id)) == [
        ("source-0", "https://orchard.example/"),
        ("source-1", "https://greenhouse.example/"),
    ]
    result = client.get(f"/api/projects/{project_id}/ingestion-runs/{run['id']}")
    assert result.json()["status"] == "succeeded"
    assert result.json()["completion"] == "complete"


def test_sources_sharing_a_site_crawl_one_after_another(api):
    client, engine, project_id, _, config, _ = api
    origins = ["https://orchard.example", "https://greenhouse.example"]
    payload = sites_draft(config, origins + ["https://orchard.example"])
    payload["execution"]["nodes"][2]["config"]["selection"]["url"] = (
        "https://orchard.example/harvest"
    )
    version = save(client, project_id, payload)
    run = start_run(client, project_id, version)
    pages = site_pages(origins)
    pages["https://orchard.example/harvest"] = [
        page("https://orchard.example/harvest", html("Harvest", "Harvest is in May."))
    ]
    double = ConcurrentDouble(pages, hold=0.2)

    index_id = publish(engine, run["id"], lambda: double)

    # The two orchard sources share a lane; the greenhouse runs beside it.
    assert double.peak == 2
    orchard = [url for url in double.crawled if "orchard" in url]
    assert orchard == ["https://orchard.example/", "https://orchard.example/harvest"]
    assert len(memberships(engine, index_id)) == 3


def test_concurrent_crawls_stay_within_the_limit_and_the_database_pool(
    api, monkeypatch
):
    client, engine, project_id, _, config, _ = api
    monkeypatch.setattr(settings, "website_run_source_concurrency", 2)
    origins = [f"https://site{number}.example" for number in range(4)]
    version = save(client, project_id, sites_draft(config, origins))
    run = start_run(client, project_id, version)
    double = ConcurrentDouble(site_pages(origins), hold=0.2)
    checked_out = {"now": 0, "peak": 0}
    lock = threading.Lock()

    def on_checkout(*_):
        with lock:
            checked_out["now"] += 1
            checked_out["peak"] = max(checked_out["peak"], checked_out["now"])

    def on_checkin(*_):
        with lock:
            checked_out["now"] -= 1

    event.listen(engine, "checkout", on_checkout)
    event.listen(engine, "checkin", on_checkin)
    try:
        index_id = publish(engine, run["id"], lambda: double)
    finally:
        event.remove(engine, "checkout", on_checkout)
        event.remove(engine, "checkin", on_checkin)

    assert double.peak == 2
    assert len(memberships(engine, index_id)) == 4
    # The crawls never need more connections than the pool holds without overflow.
    assert checked_out["peak"] <= engine.pool.size()


def test_a_site_failing_while_another_crawls_still_publishes(api):
    client, engine, project_id, _, config, _ = api
    origins = ["https://orchard.example", "https://greenhouse.example"]
    version = save(client, project_id, sites_draft(config, origins))
    run = start_run(client, project_id, version)
    pages = site_pages(origins)
    pages["https://greenhouse.example/"] = ConnectorIssue(
        code="sitemap_unavailable",
        message="The sitemap could not be read.",
        retryable=False,
    )

    index_id = publish(engine, run["id"], lambda: ConcurrentDouble(pages))

    assert memberships(engine, index_id) == [("source-0", "https://orchard.example/")]
    result = client.get(f"/api/projects/{project_id}/ingestion-runs/{run['id']}").json()
    assert result["completion"] == "with_warnings"
    statuses = {
        item["source_node_id"]: item["status"] for item in result["source_outcomes"]
    }
    assert statuses == {"source-0": "succeeded", "source-1": "failed"}


def source(node_id, *origins):
    return SimpleNamespace(
        id=node_id, config=SimpleNamespace(allowed_origins=list(origins))
    )


def test_sources_with_overlapping_origins_share_a_lane():
    a = source("a", "https://one.example")
    b = source("b", "https://two.example")
    c = source("c", "https://three.example", "https://one.example/")
    d = source("d", "https://four.example", "https://two.example")
    e = source("e", "https://five.example")

    lanes = _origin_lanes([a, b, c, d, e])

    assert [[node.id for node in lane] for lane in lanes] == [
        ["a", "c"],
        ["b", "d"],
        ["e"],
    ]


def test_a_stopped_run_refuses_further_pages():
    calls = []
    store = SimpleNamespace(
        commit=lambda *args: calls.append(args) or True, max_pages=3
    )
    stop = threading.Event()
    wrapped = _StoppableStore(store, stop)

    assert wrapped.commit("page") is True
    stop.set()
    assert wrapped.commit("page") is False
    assert calls == [("page",)]
    assert wrapped.max_pages == 3
