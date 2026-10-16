"""Recommended Website settings, spec 0011 Slice 1."""

import json
import subprocess
import sys
from copy import deepcopy
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session

from app.connectors.base import ConnectorFailure, ConnectorIssue
from app.connectors.safe_http import SafeHttpClient
from app.connectors.website import WebsiteConnector
from app.connectors.website_probe import (
    MAX_REQUESTS,
    ProbeSignals,
    _ProbeTransport,
    probe_website,
    same_site,
    same_site_origins,
)
from app.core.auth import Principal, current_principal
from app.core.config import settings
from app.main import app
from app.models.pipeline import Pipeline, PipelineVersion
from app.models.security import ProjectMembership, UserIdentity
from app.models.setting_recommendation import SettingRecommendation
from app.schemas.ingestion import IngestionExecution
from app.services import previews
from app.services.website_recommendation import recommend
from app.workers.dispatcher import dispatch_setting_recommendations_once
from app.workers.processing import now
from app.workers.setting_recommendations import process_recommendation
from test_documents import documents_api  # noqa: F401
from test_ingestion_contracts import ingestion_draft
from website_probe_sites import SITES
from website_probe_sites import run as run_site

PUBLIC_IP = "93.184.216.34"
UA = "RecommendationTest/1.0"


def public_resolver(host, port, type):
    return [(2, type, 6, "", (PUBLIC_IP, port))]


def private_resolver(host, port, type):
    return [(2, type, 6, "", ("10.0.0.7", port))]


class FakeClock:
    """Monotonic time that only moves when the code sleeps."""

    def __init__(self):
        self.value = 1000.0
        self.sleeps = []

    def __call__(self):
        return self.value

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.value += seconds


class Transport:
    def __init__(self, responses, clock=None):
        self.responses = responses
        self.clock = clock
        self.calls = []
        self.times = []

    def request(self, url, address, timeout, headers, max_bytes):
        self.calls.append(url)
        if self.clock is not None:
            self.times.append(self.clock())
        response = self.responses.get(url)
        if response is None:
            raise ConnectorFailure(
                ConnectorIssue(
                    code="missing", message="No controlled response.", retryable=False
                )
            )
        return response


HTML = {"content-type": "text/html"}
ROBOTS = (200, {"content-type": "text/plain"}, b"User-agent: *\nAllow: /\n")


def site(**extra):
    responses = {
        "https://docs.example/robots.txt": ROBOTS,
        "https://docs.example/docs": (301, {**HTML, "location": "/docs/"}, b""),
        "https://docs.example/docs/": (
            200,
            HTML,
            b"<main><h1>Docs</h1><p>Secret page words.</p>"
            b"<a href='/docs/a'>A</a><a href='/docs/b'>B</a><a href='/'>Home</a></main>",
        ),
    }
    responses.update(extra)
    return Transport(responses)


def run_probe(transport, url, resolver=public_resolver, clock=None):
    clock = clock or FakeClock()
    client = SafeHttpClient(resolver=resolver, transport=transport)
    return probe_website(
        {"mode": "crawl", "start_url": url},
        connector_factory=lambda: WebsiteConnector(client=client, sleeper=clock.sleep),
        user_agent=UA,
        clock=clock,
        sleeper=clock.sleep,
    )


def inputs(url, other=0):
    return {
        "selection": {"mode": "crawl", "start_url": url},
        "entered_url": url,
        "other_sources_max_pages": other,
        "page_ceiling": 200,
    }


def field(result, path):
    return next(item for item in result.fields if item["path"] == path)


def test_redirect_to_the_folder_scopes_the_crawl_to_it():
    transport = site()
    signals = run_probe(transport, "https://docs.example/docs")
    assert signals.start_page["final_url"] == "https://docs.example/docs/"
    result = recommend(signals, inputs("https://docs.example/docs"), settings)
    include = field(result, "include_path_prefixes")
    assert include["value"] == ["/docs/"]
    assert include["basis"] == "computed"
    assert include["rationale_code"] == "include_redirect_folder"
    assert "/docs/" in include["rationale"]
    origins = field(result, "allowed_origins")
    assert origins["value"] == ["https://docs.example"]
    assert origins["rationale_code"] == "origins_start"
    assert field(result, "requests_per_second")["value"] == 2
    assert field(result, "requests_per_second")["rationale_code"] == "rps_default"
    # No sitemap and no readable linked page: crawl, an open frontier and the
    # default depth (Slice 2 rules).
    assert field(result, "selection")["rationale_code"] == "mode_crawl_no_sitemap"
    assert field(result, "max_pages")["rationale_code"] == "pages_crawl_open"
    assert field(result, "max_depth")["basis"] == "default"
    assert result.recommended["include_path_prefixes"] == ["/docs/"]
    assert result.recommended["max_pages"] == 50
    # Measurements only: no page text in the stored signals (D7).
    stored = json.dumps(signals.as_json())
    assert "Secret page words" not in stored and "<main>" not in stored
    assert len(signals.requests) <= MAX_REQUESTS
    assert all("?" not in item["url"] for item in signals.requests)


def test_crawl_delay_slows_the_probe_and_the_recommendation():
    clock = FakeClock()
    transport = site(
        **{
            "https://docs.example/robots.txt": (
                200,
                {"content-type": "text/plain"},
                b"User-agent: *\nCrawl-delay: 4\n",
            )
        }
    )
    transport.clock = clock
    signals = run_probe(transport, "https://docs.example/docs", clock=clock)
    assert signals.robots["crawl_delay"] == 4
    # Requests to the origin were at least the crawl delay apart.
    assert len(transport.times) >= 3
    assert all(
        later - earlier >= 4 - 1e-6
        for earlier, later in zip(transport.times, transport.times[1:])
    )
    result = recommend(signals, inputs("https://docs.example/docs"), settings)
    speed = field(result, "requests_per_second")
    assert speed["value"] == 0.25 and speed["rationale_code"] == "rps_crawl_delay"


def test_robots_blocking_the_start_url_fails_the_probe():
    transport = site(
        **{
            "https://docs.example/robots.txt": (
                200,
                {"content-type": "text/plain"},
                b"User-agent: *\nDisallow: /docs\n",
            )
        }
    )
    with pytest.raises(ConnectorFailure) as caught:
        run_probe(transport, "https://docs.example/docs")
    assert caught.value.issue.code == "robots_blocks_start"
    assert transport.calls == ["https://docs.example/robots.txt"]


def test_private_address_is_blocked_before_any_request():
    transport = site()
    with pytest.raises(ConnectorFailure) as caught:
        run_probe(transport, "https://docs.example/docs", resolver=private_resolver)
    assert caught.value.issue.code == "blocked_destination"
    assert transport.calls == []


def test_redirect_to_another_site_adds_nothing():
    transport = site(
        **{
            "https://docs.example/docs": (
                301,
                {**HTML, "location": "https://elsewhere.example/docs/"},
                b"",
            ),
            "https://elsewhere.example/docs/": (200, HTML, b"<p>Other</p>"),
        }
    )
    signals = run_probe(transport, "https://docs.example/docs")
    assert "https://elsewhere.example/docs/" not in transport.calls
    assert signals.warnings == ["redirect_other_site"]
    result = recommend(signals, inputs("https://docs.example/docs"), settings)
    assert field(result, "allowed_origins")["value"] == ["https://docs.example"]
    assert [item["code"] for item in result.warnings] == ["redirect_other_site"]
    # Without the final page the scope is today's derivation, never wider.
    assert field(result, "include_path_prefixes")["value"] == []


def test_same_site_redirect_adds_the_final_origin():
    transport = Transport(
        {
            "http://example.org/robots.txt": (404, {}, b""),
            "http://example.org/guide/": (
                301,
                {**HTML, "location": "https://www.example.org/guide/"},
                b"",
            ),
            "https://www.example.org/robots.txt": (404, {}, b""),
            "https://www.example.org/guide/": (200, HTML, b"<p>Guide</p>"),
        }
    )
    signals = run_probe(transport, "http://example.org/guide/")
    result = recommend(signals, inputs("http://example.org/guide/"), settings)
    origins = field(result, "allowed_origins")
    assert origins["value"] == ["http://example.org", "https://www.example.org"]
    assert origins["rationale_code"] == "origins_redirect"
    assert field(result, "include_path_prefixes")["value"] == ["/guide/"]


def test_links_into_the_path_scope_the_section():
    transport = Transport(
        {
            "https://docs.example/robots.txt": ROBOTS,
            "https://docs.example/manual": (
                200,
                HTML,
                b"<a href='/manual/a'>a</a><a href='/manual/b'>b</a>"
                b"<a href='/blog'>blog</a><a href='https://other.example/x'>x</a>",
            ),
        }
    )
    signals = run_probe(transport, "https://docs.example/manual")
    assert signals.start_page["links_same_origin"] == 3
    assert signals.start_page["links_below_path"] == 2
    result = recommend(signals, inputs("https://docs.example/manual"), settings)
    include = field(result, "include_path_prefixes")
    assert include["value"] == ["/manual/"]
    assert include["rationale_code"] == "include_links_folder"


def test_same_site_rules():
    assert same_site("http://example.org", "https://www.example.org")
    assert same_site("https://www.example.org", "https://example.org")
    assert not same_site("https://example.org", "http://example.org")
    assert not same_site("https://example.org", "https://docs.example.org")
    assert not same_site("https://example.org", "https://example.org:8443")
    assert same_site_origins("https://example.org") == [
        "https://example.org",
        "https://www.example.org",
    ]
    assert same_site_origins("https://93.184.216.34") == ["https://93.184.216.34"]


def test_request_bound_is_enforced_at_the_transport():
    clock = FakeClock()
    transport = _ProbeTransport(
        Transport({"https://docs.example/": (200, HTML, b"ok")}),
        clock=clock,
        sleeper=clock.sleep,
        deadline=clock() + 10_000,
    )
    for _ in range(MAX_REQUESTS):
        transport.request("https://docs.example/", PUBLIC_IP, 5, {}, 1024)
    with pytest.raises(ConnectorFailure) as caught:
        transport.request("https://docs.example/", PUBLIC_IP, 5, {}, 1024)
    assert caught.value.issue.code == "probe_request_limit"
    assert len(transport.records) == MAX_REQUESTS
    # One request per second per origin.
    assert all(value >= 1 for value in clock.sleeps)


def test_probe_deadline_stops_waiting():
    clock = FakeClock()
    transport = _ProbeTransport(
        Transport({"https://docs.example/": (200, HTML, b"ok")}),
        clock=clock,
        sleeper=clock.sleep,
        deadline=clock() + 1.5,
    )
    transport.intervals["https://docs.example"] = 5
    transport.request("https://docs.example/", PUBLIC_IP, 5, {}, 1024)
    with pytest.raises(ConnectorFailure) as caught:
        transport.request("https://docs.example/", PUBLIC_IP, 5, {}, 1024)
    assert caught.value.issue.code == "deadline_exceeded"


def test_slow_site_and_page_budget():
    signals = ProbeSignals(
        probe_mode="crawl",
        entered_url="https://docs.example/docs/",
        entered_origin="https://docs.example",
        robots={"crawl_delay": None},
        start_page={
            "final_url": "https://docs.example/docs/",
            "median_response_ms": 2500,
            "throttled": 0,
        },
    )
    result = recommend(signals, inputs("https://docs.example/docs/", 2480), settings)
    assert field(result, "requests_per_second")["value"] == 1
    assert field(result, "requests_per_second")["rationale_code"] == "rps_slow_site"
    pages = field(result, "max_pages")
    assert pages["value"] == 20 and pages["rationale_code"] == "pages_budget"


# PostgreSQL: API, worker, dispatcher and provenance.


def controlled_probe(selection, on_step):
    on_step("robots", 10)
    on_step("start_page", 40)
    return run_probe(site(), selection["start_url"])


def request_body(node="source-0", url="https://docs.example/docs", **extra):
    return {
        "target": "website",
        "source_node_id": node,
        "selection": {"mode": "crawl", "start_url": url},
        **extra,
    }


@pytest.fixture
def recommendation_api(documents_api, monkeypatch):  # noqa: F811
    client, engine, project_id, other_project_id = documents_api
    monkeypatch.setattr(settings, "setting_recommendations_enabled", True)
    yield client, engine, project_id, other_project_id
    with Session(engine) as session:
        projects = [UUID(project_id), UUID(other_project_id)]
        session.execute(
            delete(PipelineVersion).where(PipelineVersion.project_id.in_(projects))
        )
        session.execute(delete(Pipeline).where(Pipeline.project_id.in_(projects)))
        session.commit()


def started(client, project_id, **extra):
    response = client.post(
        f"/api/projects/{project_id}/setting-recommendations",
        json=request_body(**extra),
    )
    assert response.status_code == 202, response.text
    return response.json()


def succeeded(client, engine, project_id, **extra):
    row = started(client, project_id, **extra)
    process_recommendation(UUID(row["id"]), engine, probe=controlled_probe)
    result = client.get(
        f"/api/projects/{project_id}/setting-recommendations/{row['id']}"
    ).json()
    assert result["status"] == "succeeded", result
    return result


def test_migration_0048_round_trip(database):
    engine, env = database
    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0047"], env=env, check=True
    )
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT to_regclass('public.setting_recommendations')")
            )
            is None
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns WHERE "
                    "table_name='pipeline_versions' AND column_name='settings_provenance'"
                )
            )
            == 0
        )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True
    )
    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT to_regclass('public.setting_recommendations')")
        )


def test_gate_off_keeps_today_behaviour(documents_api, monkeypatch):  # noqa: F811
    client, _, project_id, _ = documents_api
    monkeypatch.setattr(settings, "setting_recommendations_enabled", False)
    capabilities = client.get(f"/api/projects/{project_id}/ingestion-capabilities")
    assert capabilities.json()["setting_recommendations"] == {
        "enabled": False,
        "page_ceiling": settings.setting_recommendations_page_ceiling,
    }
    response = client.post(
        f"/api/projects/{project_id}/setting-recommendations", json=request_body()
    )
    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Setting recommendations are turned off on this server."
    )


def test_recommendation_job_is_project_scoped_and_computed(recommendation_api):
    client, engine, project_id, other_project_id = recommendation_api
    capabilities = client.get(f"/api/projects/{project_id}/ingestion-capabilities")
    assert capabilities.json()["setting_recommendations"]["enabled"] is True
    row = started(client, project_id)
    assert row["status"] == "queued" and row["recommended"] is None
    assert (
        client.get(
            f"/api/projects/{other_project_id}/setting-recommendations/{row['id']}"
        ).status_code
        == 404
    )
    process_recommendation(UUID(row["id"]), engine, probe=controlled_probe)
    result = client.get(
        f"/api/projects/{project_id}/setting-recommendations/{row['id']}"
    ).json()
    assert result["status"] == "succeeded" and result["progress"] == 100
    assert result["recommended"]["include_path_prefixes"] == ["/docs/"]
    include = next(
        item for item in result["fields"] if item["path"] == "include_path_prefixes"
    )
    assert include["rationale_code"] == "include_redirect_folder"
    assert result["evidence"]["requests"]
    assert "Secret page words" not in json.dumps(result)


def test_viewer_cannot_start_an_analysis(recommendation_api):
    client, engine, project_id, _ = recommendation_api
    user_id = uuid4()
    principal = Principal(user_id, f"viewer-{user_id}", None, "oidc")
    with Session(engine) as session:
        session.add(UserIdentity(id=user_id, external_subject=principal.subject))
        session.flush()
        session.add(
            ProjectMembership(
                project_id=UUID(project_id), user_id=user_id, role="viewer"
            )
        )
        session.commit()
    app.dependency_overrides[current_principal] = lambda: principal
    try:
        response = client.post(
            f"/api/projects/{project_id}/setting-recommendations",
            json=request_body(),
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(current_principal, None)
        with Session(engine) as session:
            session.execute(
                delete(ProjectMembership).where(ProjectMembership.user_id == user_id)
            )
            session.execute(delete(UserIdentity).where(UserIdentity.id == user_id))
            session.commit()


def test_one_active_analysis_per_node_cache_refresh_and_limit(
    recommendation_api, monkeypatch
):
    client, engine, project_id, _ = recommendation_api
    first = started(client, project_id)
    second = started(client, project_id)
    other_node = started(client, project_id, node="source-1")
    with Session(engine) as session:
        assert session.get(SettingRecommendation, UUID(first["id"])).status == (
            "cancelled"
        )
        assert session.get(SettingRecommendation, UUID(second["id"])).status == (
            "queued"
        )
        assert session.get(SettingRecommendation, UUID(other_node["id"])).status == (
            "queued"
        )
    process_recommendation(UUID(second["id"]), engine, probe=controlled_probe)
    # The same inputs within 24 hours return the stored result without a probe.
    cached = started(client, project_id)
    assert cached["id"] == second["id"] and cached["status"] == "succeeded"
    refreshed = started(client, project_id, refresh=True)
    assert refreshed["id"] != second["id"] and refreshed["status"] == "queued"
    monkeypatch.setattr(settings, "setting_recommendations_per_project_hour", 4)
    response = client.post(
        f"/api/projects/{project_id}/setting-recommendations",
        json=request_body(node="source-2"),
    )
    assert response.status_code == 429
    assert "Analysis limit reached" in response.json()["detail"]
    # Cache hits do not count against the limit.
    process_recommendation(UUID(refreshed["id"]), engine, probe=controlled_probe)
    assert started(client, project_id)["status"] == "succeeded"


def test_fenced_token_rejects_a_stale_worker(recommendation_api):
    client, engine, project_id, _ = recommendation_api
    row = started(client, project_id)
    newer = uuid4()

    def overtaken(selection, on_step):
        signals = controlled_probe(selection, lambda *args: None)
        # A newer attempt took over this job while the probe was running.
        with Session(engine) as session:
            session.execute(
                update(SettingRecommendation)
                .where(SettingRecommendation.id == UUID(row["id"]))
                .values(execution_token=newer)
            )
            session.commit()
        return signals

    process_recommendation(UUID(row["id"]), engine, probe=overtaken)
    with Session(engine) as session:
        stored = session.get(SettingRecommendation, UUID(row["id"]))
        assert stored.status == "running" and stored.execution_token == newer
        assert stored.recommended is None

    # A cancelled job stops at its next step.
    cancelled = started(client, project_id, node="source-9")
    steps = []

    def cancelled_midway(selection, on_step):
        client.post(
            f"/api/projects/{project_id}/setting-recommendations/"
            f"{cancelled['id']}/cancel"
        )
        steps.append("probe")
        on_step("start_page", 40)
        steps.append("continued")
        return controlled_probe(selection, on_step)

    process_recommendation(UUID(cancelled["id"]), engine, probe=cancelled_midway)
    assert steps == ["probe"]
    with Session(engine) as session:
        stored = session.get(SettingRecommendation, UUID(cancelled["id"]))
        assert stored.status == "cancelled" and stored.recommended is None


def test_stale_running_recovery_requeues_once_then_fails(recommendation_api):
    client, engine, project_id, _ = recommendation_api
    row = started(client, project_id)
    sent = []

    def make_stale():
        with Session(engine) as session:
            session.execute(
                update(SettingRecommendation)
                .where(SettingRecommendation.id == UUID(row["id"]))
                .values(
                    status="running",
                    execution_token=uuid4(),
                    updated_at=now() - timedelta(seconds=400),
                )
            )
            session.commit()

    make_stale()
    dispatch_setting_recommendations_once(engine, send=sent.append)
    with Session(engine) as session:
        stored = session.get(SettingRecommendation, UUID(row["id"]))
        assert (stored.status, stored.failures) == ("queued", 1)
        assert stored.execution_token is None
    assert UUID(row["id"]) in sent
    make_stale()
    dispatch_setting_recommendations_once(engine, send=sent.append)
    with Session(engine) as session:
        stored = session.get(SettingRecommendation, UUID(row["id"]))
        assert (stored.status, stored.failures) == ("failed", 2)
        assert stored.finished_at is not None


def test_terminal_rows_are_never_updated(recommendation_api):
    client, engine, project_id, _ = recommendation_api
    result = succeeded(client, engine, project_id)

    def snapshot():
        with Session(engine) as session:
            stored = session.get(SettingRecommendation, UUID(result["id"]))
            return {
                column.name: getattr(stored, column.name)
                for column in SettingRecommendation.__table__.columns
            }

    before = snapshot()
    cancel = client.post(
        f"/api/projects/{project_id}/setting-recommendations/{result['id']}/cancel"
    )
    assert cancel.status_code == 200 and cancel.json()["status"] == "succeeded"
    process_recommendation(UUID(result["id"]), engine, probe=controlled_probe)
    dispatch_setting_recommendations_once(engine, send=lambda _: None)
    started(client, project_id, refresh=True)
    assert snapshot() == before


def save_payload(config_update=None):
    payload = ingestion_draft()
    source = payload["execution"]["nodes"][0]
    source["config"] = {
        "kind": "website",
        "selection": {"mode": "crawl", "start_url": "https://docs.example/docs"},
        "allowed_origins": ["https://docs.example"],
        "include_path_prefixes": ["/docs/"],
        "exclude_path_prefixes": [],
        "max_pages": 50,
        "max_depth": 3,
        "requests_per_second": 2,
        **(config_update or {}),
    }
    return payload


def test_provenance_records_basis_without_changing_execution(recommendation_api):
    client, engine, project_id, other_project_id = recommendation_api
    result = succeeded(client, engine, project_id)
    foreign = succeeded(client, engine, other_project_id)
    base = f"/api/projects/{project_id}/pipelines"

    plain = client.post(base, json=save_payload())
    assert plain.status_code == 201, plain.text
    assert plain.json()["settings_provenance"] is None

    applied = client.post(
        base, json={**save_payload(), "recommendation_ids": [result["id"]]}
    )
    assert applied.status_code == 201, applied.text
    version = applied.json()
    assert version["execution"] == plain.json()["execution"]
    with Session(engine) as session:
        rows = session.scalars(
            select(PipelineVersion).where(
                PipelineVersion.id.in_([UUID(version["id"]), UUID(plain.json()["id"])])
            )
        ).all()
        stored = {str(row.id): row for row in rows}
        assert json.dumps(stored[version["id"]].execution, sort_keys=True) == (
            json.dumps(stored[plain.json()["id"]].execution, sort_keys=True)
        )
        assert previews._configuration_hash(
            IngestionExecution.model_validate(stored[version["id"]].execution)
        ) == previews._configuration_hash(
            IngestionExecution.model_validate(stored[plain.json()["id"]].execution)
        )
    node = version["settings_provenance"]["nodes"]["source-0"]
    assert node["recommendation_id"] == result["id"]
    assert node["entered_url"] == "https://docs.example/docs"
    include = node["fields"]["include_path_prefixes"]
    assert include["basis"] == "computed" and include["recommended"] == ["/docs/"]
    # Slice 2 computes the page limit; with no readable linked page the depth
    # keeps its default.
    assert node["fields"]["max_pages"]["basis"] == "computed"
    assert node["fields"]["max_depth"]["basis"] == "default"

    edited = client.post(
        f"{base}/{version['pipeline_id']}/versions",
        json={
            **save_payload({"include_path_prefixes": ["/"]}),
            "recommendation_ids": [result["id"], foreign["id"]],
        },
    )
    assert edited.status_code == 201, edited.text
    nodes = edited.json()["settings_provenance"]["nodes"]
    # The foreign project's recommendation is skipped, never read.
    assert list(nodes) == ["source-0"]
    include = nodes["source-0"]["fields"]["include_path_prefixes"]
    assert include["basis"] == "user"
    assert include["recommended"] == ["/docs/"] and include["saved"] == ["/"]
    assert nodes["source-0"]["fields"]["allowed_origins"]["basis"] == "computed"
    assert (
        client.get(
            f"{base}/{version['pipeline_id']}/versions/{edited.json()['id']}"
        ).json()["settings_provenance"]
        == edited.json()["settings_provenance"]
    )

    only_foreign = client.post(
        f"{base}/{version['pipeline_id']}/versions",
        json={**save_payload(), "recommendation_ids": [foreign["id"]]},
    )
    assert only_foreign.status_code == 201
    assert only_foreign.json()["settings_provenance"] is None

    queued = started(client, project_id, node="source-0", refresh=True)
    unavailable = client.post(
        f"{base}/{version['pipeline_id']}/versions",
        json={**save_payload(), "recommendation_ids": [queued["id"]]},
    )
    assert unavailable.status_code == 201
    assert unavailable.json()["settings_provenance"]["nodes"]["source-0"]["status"] == (
        "recommendation_unavailable"
    )

    duplicate = deepcopy(save_payload())
    duplicate["recommendation_ids"] = [result["id"], result["id"]]
    assert client.post(base, json=duplicate).status_code == 422


@pytest.mark.parametrize(
    ("site", "mode", "code"),
    [
        ("docs_sitemap", "sitemap", "mode_sitemap"),
        ("docs_crawl", "crawl", "mode_crawl_no_sitemap"),
        ("sitemap_input", "sitemap", "mode_sitemap_input"),
        ("url_list", "url_list", "mode_url_list"),
        ("single_url", "single_url", "mode_single_url"),
    ],
)
def test_each_input_mode_runs_through_the_api(recommendation_api, site, mode, code):
    client, engine, project_id, _ = recommendation_api
    selection, responses = SITES[site]()
    response = client.post(
        f"/api/projects/{project_id}/setting-recommendations",
        json={
            "target": "website",
            "source_node_id": f"source-{site}",
            "selection": selection,
            "other_sources_max_pages": 100,
        },
    )
    assert response.status_code == 202, response.text
    row = response.json()
    steps = []

    def probe(selection, on_step):
        steps.append(selection["mode"])
        return run_site(selection, responses)[0]

    process_recommendation(UUID(row["id"]), engine, probe=probe)
    result = client.get(
        f"/api/projects/{project_id}/setting-recommendations/{row['id']}"
    ).json()
    assert steps == [selection["mode"]]
    assert result["status"] == "succeeded", result
    assert result["recommended"]["selection"]["mode"] == mode
    by_path = {item["path"]: item for item in result["fields"]}
    assert by_path["selection"]["rationale_code"] == code
    assert result["recommended"]["max_pages"] + 100 <= 2500
    assert set(result["evidence"]) >= {"requests", "robots", "timing"}
    with Session(engine) as session:
        stored = session.get(SettingRecommendation, UUID(row["id"]))
        assert len(json.dumps(stored.signals).encode()) <= 64 * 1024


def test_a_failed_probe_records_its_warning(recommendation_api):
    client, engine, project_id, _ = recommendation_api
    row = started(client, project_id, url="https://docs.example/blocked/")

    def blocked(selection, on_step):
        return run_site(
            selection,
            {
                "https://docs.example/robots.txt": (
                    200,
                    {"content-type": "text/plain"},
                    b"User-agent: *\nAllow: /docs\n\nDisallow: /blocked\n",
                )
            },
        )[0]

    process_recommendation(UUID(row["id"]), engine, probe=blocked)
    result = client.get(
        f"/api/projects/{project_id}/setting-recommendations/{row['id']}"
    ).json()
    assert result["status"] == "failed" and result["recommended"] is None
    assert [item["code"] for item in result["warnings"]] == ["robots_blocks_start"]
    assert "robots.txt" in result["error"]
