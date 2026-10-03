import gzip
import socket
import threading
import time
from datetime import datetime, timezone
from uuid import UUID
from urllib.parse import urlsplit

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors.base import ConnectorFailure, ConnectorIssue
from app.connectors.safe_http import (
    SafeHttpClient,
    StdlibTransport,
    canonical_url,
    resolve_public,
)
from app.connectors import website
from app.connectors.website import (
    PriorWebsiteRevision,
    WebsiteArtifact,
    WebsiteConnector,
    WebsiteScopeTooLarge,
    resolve_website_fetch_policy,
    strip_tracking,
)
from app.core.config import settings
from app.models.document import ProcessingRun
from app.models.index import IndexVersion
from app.models.preview import SourcePreview
from app.providers import embeddings
from app.schemas.ingestion import WebsiteConfig
from app.services.website_ingestion import page_warnings
from app.workers.previews import process_preview
from test_documents import documents_api  # noqa: F401
from test_ingestion_contracts import ingestion_draft


PUBLIC_IP = "93.184.216.34"


def public_resolver(host, port, type):
    return [(2, type, 6, "", (PUBLIC_IP, port))]


class TransportDouble:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def request(self, url, address, timeout, headers, max_bytes):
        self.calls.append((url, address, timeout, headers, max_bytes))
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        status, headers, body = response
        if len(body) > max_bytes:
            raise ConnectorFailure(
                ConnectorIssue(
                    code="response_too_large",
                    message="The website response exceeded its byte limit.",
                    retryable=False,
                )
            )
        return status, headers, body


def config(**overrides):
    value = {
        "kind": "website",
        "selection": {"mode": "crawl", "start_url": "https://public.example/"},
        "allowed_origins": ["https://public.example"],
        "include_path_prefixes": [],
        "exclude_path_prefixes": ["/admin"],
        "max_pages": 10,
        "max_depth": 2,
        "requests_per_second": 5,
    }
    value.update(overrides)
    return value


def policy(value=None, **overrides):
    """The resolved policy, fetching one page at a time unless a test says so."""
    resolved = resolve_website_fetch_policy(value or config(), settings)
    return resolved.model_copy(update={"fetch_concurrency": 1, **overrides})


def test_policy_derives_byte_budget_and_deadline_from_server_settings():
    big = resolve_website_fetch_policy(
        config(max_pages=1000, requests_per_second=2), settings
    )
    assert big.max_total_bytes == settings.website_max_total_bytes_cap
    assert big.max_response_bytes == settings.website_max_response_bytes
    # 1000 pages plus robots.txt at 2 req/s need ~500 s; the deadline allows that.
    assert 1001 / 2 < big.deadline_seconds <= settings.website_deadline_max_seconds
    assert big.user_agent == settings.website_user_agent
    assert big.respect_robots is True

    small = resolve_website_fetch_policy(config(max_pages=3), settings)
    assert small.max_total_bytes == 3 * settings.website_max_response_bytes
    assert small.deadline_seconds == settings.website_deadline_min_seconds

    slow = resolve_website_fetch_policy(
        config(max_pages=500, requests_per_second=0.2), settings
    )
    assert slow.deadline_seconds == settings.website_deadline_max_seconds

    single = resolve_website_fetch_policy(
        config(selection={"mode": "single_url", "url": "https://public.example/"}),
        settings,
    )
    assert (single.max_pages, single.max_depth) == (1, 0)


def test_policy_rejects_a_scope_that_cannot_finish_in_time():
    with pytest.raises(WebsiteScopeTooLarge, match="Lower maximum pages"):
        resolve_website_fetch_policy(
            config(max_pages=1000, requests_per_second=0.1), settings
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("user_agent", "custom"),
        ("respect_robots", False),
        ("deadline_seconds", 10),
        ("concurrency", 2),
        ("max_response_bytes", 1024),
        ("max_total_bytes", 4096),
        ("request_timeout_seconds", 5),
        ("redirect_limit", 2),
    ],
)
def test_server_owned_limits_are_rejected_in_node_settings(field, value):
    with pytest.raises(ValidationError, match="Extra inputs"):
        WebsiteConfig.model_validate(config(**{field: value}))


def test_url_list_longer_than_max_pages_is_rejected_on_the_field():
    with pytest.raises(ValidationError) as caught:
        WebsiteConfig.model_validate(
            config(
                selection={
                    "mode": "url_list",
                    "urls": [f"https://public.example/{n}" for n in range(3)],
                },
                max_pages=2,
            )
        )
    assert caught.value.errors()[0]["loc"] == ("max_pages",)
    assert "3 URLs" in caught.value.errors()[0]["msg"]


def test_connector_uses_the_server_user_agent_for_requests_and_robots():
    transport = TransportDouble(
        {
            "https://public.example/robots.txt": (
                200,
                {"content-type": "text/plain"},
                b"User-agent: RAGQualityStudio\nDisallow: /private\n\n"
                b"User-agent: *\nDisallow:\n",
            ),
            "https://public.example/": (
                200,
                {"content-type": "text/html"},
                b"<a href='/private/x'>Private</a>",
            ),
        }
    )
    connector = WebsiteConnector(
        client=SafeHttpClient(resolver=public_resolver, transport=transport),
        sleeper=lambda _: None,
    )
    outcomes = connector.discover_all(config(), policy())
    assert any(
        item.canonical_location == "https://public.example/private/x"
        and "robots.txt" in item.reason
        for item in outcomes
    )
    assert {call[3]["User-Agent"] for call in transport.calls} == {
        settings.website_user_agent
    }


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "224.0.0.1",
        "0.0.0.0",
        "::1",
        "fc00::1",
        "fe80::1",
        "ff02::1",
        "::",
    ],
)
def test_resolver_rejects_every_non_public_address(address):
    with pytest.raises(ConnectorFailure) as caught:
        resolve_public(
            "public.example",
            443,
            lambda host, port, type: [(2, type, 6, "", (address, port))],
        )
    assert caught.value.issue.code == "blocked_destination"


def test_canonicalization_and_credentials():
    assert (
        canonical_url("HTTPS://Example.COM:443/a/../b/#fragment")
        == "https://example.com/b/"
    )
    with pytest.raises(ConnectorFailure, match="credentials"):
        canonical_url("https://user:secret@example.com/")
    with pytest.raises(ConnectorFailure, match="HTTP or HTTPS"):
        canonical_url("file:///etc/passwd")


def test_redirect_dns_is_revalidated_and_never_reaches_private_target():
    transport = TransportDouble(
        {
            "https://public.example/": (
                302,
                {"location": "https://public.example/next"},
                b"",
            ),
            "https://public.example/next": (200, {"content-type": "text/html"}, b"ok"),
        }
    )
    resolutions = iter([PUBLIC_IP, "127.0.0.1"])

    def rebinding(host, port, type):
        return [(2, type, 6, "", (next(resolutions), port))]

    client = SafeHttpClient(resolver=rebinding, transport=transport)
    with pytest.raises(ConnectorFailure) as caught:
        client.get(
            "https://public.example/",
            user_agent="test",
            request_timeout=2,
            deadline=time.monotonic() + 5,
            redirect_limit=2,
            max_response_bytes=1000,
            max_total_bytes=2000,
            allowed=lambda _: True,
        )
    assert caught.value.issue.code == "blocked_destination"
    assert len(transport.calls) == 1


def test_redirect_cannot_escape_allowed_origin():
    transport = TransportDouble(
        {
            "https://public.example/": (
                302,
                {"location": "https://other.example/secret"},
                b"",
            )
        }
    )
    client = SafeHttpClient(resolver=public_resolver, transport=transport)
    with pytest.raises(ConnectorFailure) as caught:
        client.get(
            "https://public.example/",
            user_agent="test",
            request_timeout=2,
            deadline=time.monotonic() + 5,
            redirect_limit=2,
            max_response_bytes=1000,
            max_total_bytes=2000,
            allowed=lambda url: urlsplit(url).hostname == "public.example",
        )
    assert caught.value.issue.code == "outside_scope"
    assert len(transport.calls) == 1


def test_timeout_is_reported_as_a_safe_failed_item():
    timeout = ConnectorFailure(
        ConnectorIssue(
            code="request_timeout",
            message="The website request timed out.",
            retryable=True,
        )
    )
    transport = TransportDouble(
        {
            "https://public.example/robots.txt": (
                404,
                {"content-type": "text/plain"},
                b"",
            ),
            "https://public.example/": timeout,
        }
    )
    connector = WebsiteConnector(
        client=SafeHttpClient(resolver=public_resolver, transport=transport),
        sleeper=lambda _: None,
    )
    value = config(selection={"mode": "single_url", "url": "https://public.example/"})
    outcomes = connector.discover_all(value, policy(value))
    assert len(outcomes) == 1
    assert outcomes[0].status == "failed"
    assert outcomes[0].error_code == "request_timeout"
    assert outcomes[0].reason == "The website request timed out."


def test_validator_refresh_reuses_prior_body():
    transport = TransportDouble(
        {
            "https://public.example/robots.txt": (404, {}, b""),
            "https://public.example/": (
                304,
                {"etag": '"v1"'},
                b"",
            ),
        }
    )
    connector = WebsiteConnector(
        client=SafeHttpClient(resolver=public_resolver, transport=transport),
        sleeper=lambda _: None,
    )
    prior = PriorWebsiteRevision(
        content=b"<main><a href='/next'>Next</a></main>",
        media_type="text/html",
        etag='"v1"',
    )
    value = config(selection={"mode": "single_url", "url": "https://public.example/"})
    outcomes, artifacts = connector.fetch_all(
        value, policy(value), {"https://public.example/": prior}
    )
    assert outcomes[0].status == "included"
    assert artifacts[0].content == prior.content
    assert artifacts[0].validator_unchanged is True
    assert transport.calls[1][3]["If-None-Match"] == '"v1"'


def test_crawl_reports_included_excluded_duplicates_failures_and_robots():
    root = b"""
      <html><body>
        <a href='/guide'>Guide</a><a href='/guide#again'>Duplicate</a>
        <a href='/admin/private'>Excluded</a><a href='https://other.example/out'>Other</a>
        <a href='/blocked'>Robots</a><a href='/asset.pdf'>PDF</a>
      </body></html>
    """
    transport = TransportDouble(
        {
            "https://public.example/robots.txt": (
                200,
                {"content-type": "text/plain"},
                b"User-agent: *\nDisallow: /blocked\n",
            ),
            "https://public.example/": (200, {"content-type": "text/html"}, root),
            "https://public.example/guide": (
                200,
                {"content-type": "text/html"},
                b"<html><a href='/missing'>Missing",
            ),
            "https://public.example/asset.pdf": (
                200,
                {"content-type": "application/pdf"},
                b"not parsed",
            ),
            "https://public.example/missing": (
                404,
                {"content-type": "text/html"},
                b"missing",
            ),
        }
    )
    connector = WebsiteConnector(
        client=SafeHttpClient(resolver=public_resolver, transport=transport),
        sleeper=lambda _: None,
    )
    outcomes = connector.discover_all(config(), policy())
    by_status = {
        status: [item for item in outcomes if item.status == status]
        for status in ("included", "excluded", "duplicate", "failed")
    }
    assert {item.canonical_location for item in by_status["included"]} == {
        "https://public.example/",
        "https://public.example/guide",
    }
    assert any("origin" in item.reason for item in by_status["excluded"])
    assert any("robots.txt" in item.reason for item in by_status["excluded"])
    assert any(item.media_type == "application/pdf" for item in by_status["excluded"])
    assert [item.canonical_location for item in by_status["duplicate"]] == [
        "https://public.example/guide"
    ]
    assert by_status["failed"][0].error_code == "http_status"
    assert all(call[0] != "https://other.example/out" for call in transport.calls)


@pytest.mark.parametrize(
    "body,code",
    [
        (b"<!DOCTYPE x [<!ENTITY a 'boom'>]><urlset/>", "unsafe_sitemap"),
        (b"<urlset><url>", "invalid_sitemap"),
    ],
)
def test_sitemap_rejects_unsafe_or_malformed_xml(body, code):
    transport = TransportDouble(
        {
            "https://public.example/sitemap.xml": (
                200,
                {"content-type": "application/xml"},
                body,
            )
        }
    )
    connector = WebsiteConnector(
        client=SafeHttpClient(resolver=public_resolver, transport=transport),
        sleeper=lambda _: None,
    )
    value = config(
        selection={
            "mode": "sitemap",
            "sitemap_url": "https://public.example/sitemap.xml",
        }
    )
    with pytest.raises(ConnectorFailure) as caught:
        connector.discover_all(value, policy(value))
    assert caught.value.issue.code == code


def test_async_preview_job(documents_api, monkeypatch):  # noqa: F811
    client, engine, project_id, other_project_id = documents_api
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr("test-secret"))
    monkeypatch.setattr(settings, "embedding_dimensions", 3)
    embedding = embeddings.configured()
    payload = ingestion_draft()
    embed = next(
        node for node in payload["execution"]["nodes"] if node["type"] == "embed"
    )
    embed.update(
        provider=embedding.provider,
        model=embedding.model,
        dimensions=embedding.dimensions,
        config_version=embedding.revision,
    )
    accepted = client.post(
        f"/api/projects/{project_id}/ingestion-previews",
        json={"execution": payload["execution"]},
    )
    assert accepted.status_code == 202, accepted.text
    preview_id = accepted.json()["id"]
    recorded = accepted.json()["fetch_policies"]["source-0"]
    assert recorded["user_agent"] == settings.website_user_agent
    assert recorded["max_pages"] == 1 and recorded["respect_robots"] is True
    assert (
        client.post(
            f"/api/projects/{project_id}/ingestion-previews",
            json={"execution": payload["execution"]},
        ).status_code
        == 409
    )
    outcomes = [
        {
            "source_node_id": "source-0",
            "external_id": f"https://example.com/{number}",
            "display_name": f"Page {number}",
            "canonical_location": f"https://example.com/{number}",
            "media_type": "text/html",
            "status": status,
            "reason": f"{status} by controlled transport",
            "size_bytes": 100 + number,
            "depth": number,
            "error_code": "controlled" if status == "failed" else None,
        }
        for number, status in enumerate(["included", "excluded", "duplicate", "failed"])
    ]
    process_preview(
        UUID(preview_id),
        engine,
        connector_factory=lambda session, project, execution: outcomes,
    )
    process_preview(UUID(preview_id), engine, connector_factory=lambda *args: outcomes)
    result = client.get(
        f"/api/projects/{project_id}/source-previews/{preview_id}"
    ).json()
    assert result["status"] == "succeeded" and result["attempts"] == 1
    assert result["fetch_policies"]["source-0"] == recorded
    assert result["discovered_count"] == 4
    assert result["included_count"] == result["excluded_count"] == 1
    assert result["duplicate_count"] == result["failed_count"] == 1
    page = client.get(
        f"/api/projects/{project_id}/source-previews/{preview_id}/items?limit=2"
    ).json()
    assert page["total"] == 4 and [item["ordinal"] for item in page["items"]] == [0, 1]
    assert (
        client.get(
            f"/api/projects/{other_project_id}/source-previews/{preview_id}"
        ).status_code
        == 404
    )
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(IndexVersion)
                .where(IndexVersion.project_id == UUID(project_id))
            )
            == 0
        )
        assert session.scalar(select(func.count()).select_from(ProcessingRun)) == 0

    second = client.post(
        f"/api/projects/{project_id}/ingestion-previews",
        json={"execution": payload["execution"]},
    ).json()
    cancelled = client.post(
        f"/api/projects/{project_id}/source-previews/{second['id']}/cancel"
    ).json()
    assert cancelled["status"] == "cancelled"
    process_preview(
        UUID(second["id"]), engine, connector_factory=lambda *args: outcomes
    )
    with Session(engine) as session:
        assert session.get(SourcePreview, UUID(second["id"])).attempts == 0


def test_preview_job_saves_the_discovery_limit_marker(documents_api, monkeypatch):  # noqa: F811
    client, engine, project_id, _ = documents_api
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr("test-secret"))
    monkeypatch.setattr(settings, "embedding_dimensions", 3)
    embedding = embeddings.configured()
    payload = ingestion_draft()
    embed = next(
        node for node in payload["execution"]["nodes"] if node["type"] == "embed"
    )
    embed.update(
        provider=embedding.provider,
        model=embedding.model,
        dimensions=embedding.dimensions,
        config_version=embedding.revision,
    )
    preview_id = client.post(
        f"/api/projects/{project_id}/ingestion-previews",
        json={"execution": payload["execution"]},
    ).json()["id"]
    # The Website connector records omitted URLs as one item without a location or name.
    outcomes = [
        {
            "source_node_id": "source-0",
            "external_id": None,
            "display_name": None,
            "canonical_location": None,
            "media_type": None,
            "status": "excluded",
            "reason": "Additional URLs were omitted by the discovery limit.",
            "size_bytes": None,
            "depth": None,
            "error_code": None,
            "_kind": "website",
        }
    ]
    process_preview(UUID(preview_id), engine, connector_factory=lambda *args: outcomes)
    result = client.get(
        f"/api/projects/{project_id}/source-previews/{preview_id}"
    ).json()
    assert result["status"] == "succeeded" and result["attempts"] == 1
    items = client.get(
        f"/api/projects/{project_id}/source-previews/{preview_id}/items"
    ).json()["items"]
    assert [item["display_name"] for item in items] == ["Undiscovered website item"]


def test_trickling_response_is_bounded_by_the_request_timeout():
    """Each byte arrives inside the socket timeout; the whole read must not."""
    listener = socket.create_server(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    stop = threading.Event()

    def serve():
        connection, _ = listener.accept()
        with connection:
            connection.recv(4096)
            connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n")
            while not stop.is_set():
                try:
                    connection.sendall(b"x")
                except OSError:
                    return
                time.sleep(0.05)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    started = time.monotonic()
    try:
        with pytest.raises(ConnectorFailure) as raised:
            StdlibTransport().request(
                f"http://example.test:{port}/",
                "127.0.0.1",
                0.5,
                {"Host": f"example.test:{port}", "Connection": "close"},
                1024 * 1024,
            )
    finally:
        stop.set()
        listener.close()
    assert raised.value.issue.code == "request_timeout"
    assert time.monotonic() - started < 2


@pytest.mark.parametrize("chunks", [[b"x" * 5000], [b"x" * 70000], [b"ab", b"cd"]])
def test_connection_close_response_with_length_is_read_completely(chunks):
    """http.client closes the socket once Content-Length bytes have arrived."""
    body = b"".join(chunks)
    listener = socket.create_server(("127.0.0.1", 0))
    port = listener.getsockname()[1]

    def serve():
        connection, _ = listener.accept()
        with connection:
            connection.recv(4096)
            connection.sendall(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
            )
            for chunk in chunks:
                connection.sendall(chunk)
                time.sleep(0.05)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        status, headers, content = StdlibTransport().request(
            f"http://example.test:{port}/",
            "127.0.0.1",
            5,
            {"Host": f"example.test:{port}", "Connection": "close"},
            1024 * 1024,
        )
    finally:
        listener.close()
    assert (status, content) == (200, body)
    assert headers["content-length"] == str(len(body))


class SequenceTransport(TransportDouble):
    """Returns successive responses for a URL; the last one repeats."""

    def request(self, url, address, timeout, headers, max_bytes):
        self.calls.append((url, address, timeout, headers, max_bytes))
        values = self.responses[url]
        response = values.pop(0) if len(values) > 1 else values[0]
        if isinstance(response, Exception):
            raise response
        return response


class FakeClock:
    def __init__(self):
        # SafeHttpClient checks the deadline against the real monotonic clock.
        self.now = time.monotonic()
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def connector_for(transport, clock=None):
    clock = clock or FakeClock()
    return WebsiteConnector(
        client=SafeHttpClient(resolver=public_resolver, transport=transport),
        clock=clock,
        sleeper=clock.sleep,
        jitter=lambda: 0.0,
    )


HTML = {"content-type": "text/html"}
NO_ROBOTS = [(404, {}, b"")]


def page_body(text):
    return f"<main><p>{text}</p></main>".encode()


def test_sitemap_index_discovers_nested_and_gzip_sitemaps():
    index = b"""<?xml version="1.0"?>
      <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <sitemap><loc>https://public.example/post-sitemap.xml</loc></sitemap>
        <sitemap><loc>https://public.example/page-sitemap.xml.gz</loc></sitemap>
        <sitemap><loc>https://public.example/nested-index.xml</loc></sitemap>
        <sitemap><loc>https://other.example/sitemap.xml</loc></sitemap>
      </sitemapindex>"""
    posts = b"""<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://public.example/post-1</loc></url></urlset>"""
    pages = gzip.compress(
        b"<urlset><url><loc>https://public.example/about</loc></url></urlset>"
    )
    transport = SequenceTransport(
        {
            "https://public.example/robots.txt": NO_ROBOTS,
            "https://public.example/sitemap_index.xml": [
                (200, {"content-type": "application/xml"}, index)
            ],
            "https://public.example/post-sitemap.xml": [
                (200, {"content-type": "text/xml"}, posts)
            ],
            "https://public.example/page-sitemap.xml.gz": [
                (200, {"content-type": "application/x-gzip"}, pages)
            ],
            "https://public.example/nested-index.xml": [
                (200, {"content-type": "application/xml"}, b"<sitemapindex/>")
            ],
            "https://public.example/post-1": [(200, HTML, page_body("Post"))],
            "https://public.example/about": [(200, HTML, page_body("About"))],
        }
    )
    value = config(
        selection={
            "mode": "sitemap",
            "sitemap_url": "https://public.example/sitemap_index.xml",
        }
    )
    outcomes = connector_for(transport).discover_all(value, policy(value))
    by_location = {item.canonical_location: item for item in outcomes}
    assert {
        location for location, item in by_location.items() if item.status == "included"
    } == {"https://public.example/post-1", "https://public.example/about"}
    assert by_location["https://public.example/post-sitemap.xml"].status == "sitemap"
    assert by_location["https://public.example/page-sitemap.xml.gz"].status == "sitemap"
    nested = by_location["https://public.example/nested-index.xml"]
    assert "one level deep" in nested.reason
    assert "allowlist" in by_location["https://other.example/sitemap.xml"].reason
    assert all(
        call[0] != "https://other.example/sitemap.xml" for call in transport.calls
    )


def test_gzip_sitemap_is_bounded_after_decompression():
    expanded = settings.website_max_response_bytes + 1_000_000
    body = gzip.compress(b"<urlset>" + b" " * expanded + b"</urlset>")
    transport = SequenceTransport(
        {
            "https://public.example/sitemap.xml.gz": [
                (200, {"content-type": "application/gzip"}, body)
            ]
        }
    )
    value = config(
        selection={
            "mode": "sitemap",
            "sitemap_url": "https://public.example/sitemap.xml.gz",
        }
    )
    with pytest.raises(ConnectorFailure) as caught:
        connector_for(transport).discover_all(value, policy(value))
    assert caught.value.issue.code == "sitemap_too_large"
    assert caught.value.issue.retryable is False


def test_transient_status_is_retried_with_retry_after_and_attempts_recorded():
    clock = FakeClock()
    transport = SequenceTransport(
        {
            "https://public.example/robots.txt": NO_ROBOTS,
            "https://public.example/": [
                (503, {"retry-after": "4"}, b""),
                (200, HTML, page_body("Recovered")),
            ],
            "https://public.example/gone": [(503, {}, b"")],
        }
    )
    value = config(
        selection={
            "mode": "url_list",
            "urls": ["https://public.example/", "https://public.example/gone"],
        }
    )
    first, second = connector_for(transport, clock).discover_all(value, policy(value))
    assert (first.status, first.attempts) == ("included", 2)
    assert 4 in clock.sleeps  # Retry-After is honored when longer than backoff.
    assert (second.status, second.attempts) == ("failed", 3)
    assert "after 3 attempts" in second.reason
    assert (
        sum(call[0] == "https://public.example/gone" for call in transport.calls) == 3
    )


def test_retry_after_beyond_the_cap_waits_only_the_cap_and_the_deadline():
    clock = FakeClock()
    transport = SequenceTransport(
        {
            "https://public.example/robots.txt": NO_ROBOTS,
            "https://public.example/": [(429, {"retry-after": "3600"}, b"")],
        }
    )
    value = config(selection={"mode": "single_url", "url": "https://public.example/"})
    resolved = policy(value)
    outcome = connector_for(transport, clock).discover_all(value, resolved)[0]
    assert outcome.status == "failed"
    # Waited the 30 s cap once; a second wait would pass the 60 s deadline.
    assert outcome.attempts == 2
    assert resolved.retry_max_delay_seconds in clock.sleeps
    assert max(clock.sleeps) <= resolved.retry_max_delay_seconds


def test_robots_5xx_is_retried_then_fails_the_origin_once():
    transport = SequenceTransport(
        {
            "https://public.example/robots.txt": [(500, {}, b"")],
            "https://public.example/a": [(200, HTML, page_body("A"))],
            "https://public.example/b": [(200, HTML, page_body("B"))],
        }
    )
    value = config(
        selection={
            "mode": "url_list",
            "urls": ["https://public.example/a", "https://public.example/b"],
        }
    )
    outcomes = connector_for(transport).discover_all(value, policy(value))
    assert [item.error_code for item in outcomes] == ["robots_unavailable"] * 2
    assert [call[0] for call in transport.calls] == [
        "https://public.example/robots.txt"
    ] * 3

    recovering = SequenceTransport(
        {
            "https://public.example/robots.txt": [(503, {}, b""), (404, {}, b"")],
            "https://public.example/a": [(200, HTML, page_body("A"))],
        }
    )
    value = config(selection={"mode": "single_url", "url": "https://public.example/a"})
    assert connector_for(recovering).discover_all(value, policy(value))[0].status == (
        "included"
    )


def test_robots_crawl_delay_slows_but_never_speeds_up_the_crawl():
    clock = FakeClock()
    transport = SequenceTransport(
        {
            "https://public.example/robots.txt": [
                (
                    200,
                    {"content-type": "text/plain"},
                    b"User-agent: *\nCrawl-delay: 3\n",
                )
            ],
            "https://public.example/a": [(200, HTML, page_body("A"))],
            "https://public.example/b": [(200, HTML, page_body("B"))],
        }
    )
    value = config(
        selection={
            "mode": "url_list",
            "urls": ["https://public.example/a", "https://public.example/b"],
        },
        requests_per_second=5,
    )
    connector_for(transport, clock).discover_all(value, policy(value))
    assert clock.sleeps.count(3) == 2


def test_sitemap_lastmod_reuses_an_unchanged_prior_without_a_request():
    sitemap = b"""<urlset>
      <url><loc>https://public.example/old</loc><lastmod>2026-01-01</lastmod></url>
      <url><loc>https://public.example/new</loc><lastmod>2026-09-30T10:00:00Z</lastmod></url>
    </urlset>"""
    transport = SequenceTransport(
        {
            "https://public.example/robots.txt": NO_ROBOTS,
            "https://public.example/sitemap.xml": [
                (200, {"content-type": "application/xml"}, sitemap)
            ],
            "https://public.example/new": [(200, HTML, page_body("New"))],
        }
    )
    stored = datetime(2026, 6, 1, tzinfo=timezone.utc)
    priors = {
        location: PriorWebsiteRevision(
            content=page_body("Stored"), media_type="text/html", fetched_at=stored
        )
        for location in ("https://public.example/old", "https://public.example/new")
    }
    value = config(
        selection={
            "mode": "sitemap",
            "sitemap_url": "https://public.example/sitemap.xml",
        }
    )
    outcomes, artifacts = connector_for(transport).fetch_all(
        value, policy(value), priors
    )
    old = next(item for item in outcomes if item.canonical_location.endswith("/old"))
    assert old.status == "included" and old.attempts == 0
    assert "sitemap lastmod" in old.reason
    assert all(call[0] != "https://public.example/old" for call in transport.calls)
    assert {
        item.canonical_location: item.validator_unchanged for item in artifacts
    } == {
        "https://public.example/old": True,
        "https://public.example/new": False,
    }


def test_recorded_version_one_policy_does_not_retry():
    transport = SequenceTransport(
        {
            "https://public.example/robots.txt": NO_ROBOTS,
            "https://public.example/": [(503, {}, b""), (200, HTML, page_body("x"))],
        }
    )
    value = config(selection={"mode": "single_url", "url": "https://public.example/"})
    recorded = policy(value).model_dump(
        exclude={
            "retry_attempts",
            "retry_base_delay_seconds",
            "retry_max_delay_seconds",
        }
    ) | {"policy_version": 1}
    outcome = connector_for(transport).discover_all(value, recorded)[0]
    assert (outcome.status, outcome.attempts) == ("failed", 1)


def test_client_rendered_shell_is_flagged():
    def artifact(body):
        return WebsiteArtifact(
            canonical_location="https://public.example/",
            content=body,
            media_type="text/html",
            etag=None,
            last_modified=None,
            validator_unchanged=False,
            depth=0,
        )

    shell = b"<html><body><div id='root'></div><script>render()</script></body></html>"
    assert [value["code"] for value in page_warnings(artifact(shell))] == [
        "likely_client_rendered"
    ]
    assert page_warnings(artifact(page_body("Readable server text. " * 20))) == []
    # A short static page without scripts is not a JavaScript shell.
    assert page_warnings(artifact(page_body("Example domain."))) == []


def v2_execution(embedding):
    execution = ingestion_draft()["execution"]
    execution["schema_version"] = 2
    for node in execution["nodes"]:
        if node["type"] == "extract":
            node["config_version"] = "native-text-v1"
        elif node["type"] == "clean":
            node.update(profile="standard-v1", config_version="deterministic-clean-v1")
        elif node["type"] == "chunk":
            node["config_version"] = "character-window-v1"
        elif node["type"] == "embed":
            node.update(
                provider=embedding.provider,
                model=embedding.model,
                dimensions=embedding.dimensions,
                config_version=embedding.revision,
            )
    return execution


def test_preview_flags_client_rendered_page_and_records_attempts(
    documents_api,  # noqa: F811
    monkeypatch,
):
    client, engine, project_id, _ = documents_api
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr("test-secret"))
    monkeypatch.setattr(settings, "embedding_dimensions", 3)
    execution = v2_execution(embeddings.configured())
    accepted = client.post(
        f"/api/projects/{project_id}/ingestion-previews",
        json={"execution": execution},
    )
    assert accepted.status_code == 202, accepted.text
    location = "https://example.com/0"
    shell = (
        b"<html><body><main><p>Loading the application shell.</p></main>"
        b"<div id='root'></div><script>render()</script></body></html>"
    )
    outcomes = [
        {
            "source_node_id": "source-0",
            "external_id": location,
            "display_name": location,
            "canonical_location": location,
            "media_type": "text/html",
            "status": "included",
            "reason": "HTML page is within scope and fetchable.",
            "size_bytes": len(shell),
            "depth": 0,
            "error_code": None,
            "attempts": 2,
            "_kind": "website",
            "_artifact": WebsiteArtifact(
                canonical_location=location,
                content=shell,
                media_type="text/html",
                etag=None,
                last_modified=None,
                validator_unchanged=False,
                depth=0,
            ),
        },
        {
            "source_node_id": "source-0",
            "external_id": "https://example.com/sitemap.xml",
            "display_name": "https://example.com/sitemap.xml",
            "canonical_location": "https://example.com/sitemap.xml",
            "media_type": "application/xml",
            "status": "sitemap",
            "reason": "Nested sitemap; listed 1 page URLs for discovery.",
            "size_bytes": None,
            "depth": None,
            "error_code": None,
            "attempts": 1,
            "_kind": "website",
        },
    ]
    process_preview(
        UUID(accepted.json()["id"]), engine, connector_factory=lambda *args: outcomes
    )
    preview = client.get(
        f"/api/projects/{project_id}/source-previews/{accepted.json()['id']}"
    ).json()
    assert preview["status"] == "succeeded", preview["error"]
    assert (preview["included_count"], preview["excluded_count"]) == (1, 1)
    items = client.get(
        f"/api/projects/{project_id}/source-previews/{accepted.json()['id']}/items"
    ).json()["items"]
    page, sitemap = items
    assert page["attempts"] == 2
    assert "likely_client_rendered" in [value.get("code") for value in page["findings"]]
    assert sitemap["status"] == "sitemap"


def test_origin_rate_limiter_spaces_concurrent_requests_with_a_fake_clock():
    import threading

    from app.connectors.website import _OriginRateLimiter

    lock = threading.Lock()
    clock = FakeClock()

    def sleep(seconds):
        with lock:
            clock.sleeps.append(seconds)

    limiter = _OriginRateLimiter(clock, sleep)
    slots = {"https://a.example": [], "https://b.example": []}

    def worker(origin):
        for _ in range(5):
            slot = limiter.wait(origin, 0.5)
            with lock:
                slots[origin].append(slot)

    threads = [
        threading.Thread(target=worker, args=(origin,))
        for origin in slots
        for _ in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    for times in slots.values():
        times.sort()
        assert len(times) == 20
        # 2 requests per second: never three request starts inside one second.
        assert all(later - earlier >= 1.0 for earlier, later in zip(times, times[2:]))


def test_parallel_fetching_keeps_each_origin_within_its_crawl_speed():
    import threading

    lock = threading.Lock()
    starts = []

    class TimedTransport(TransportDouble):
        def request(self, url, address, timeout, headers, max_bytes):
            with lock:
                starts.append(time.monotonic())
            return super().request(url, address, timeout, headers, max_bytes)

    urls = [f"https://public.example/{number}" for number in range(7)]
    transport = TimedTransport(
        {
            "https://public.example/robots.txt": (404, {}, b""),
            **{url: (200, HTML, page_body(url)) for url in urls},
        }
    )
    value = config(selection={"mode": "url_list", "urls": urls}, requests_per_second=2)
    connector = WebsiteConnector(
        client=SafeHttpClient(resolver=public_resolver, transport=transport)
    )
    outcomes = connector.discover_all(value, policy(value, fetch_concurrency=4))
    assert sorted(item.canonical_location for item in outcomes) == sorted(urls)
    starts.sort()
    assert len(starts) == 8
    assert all(later - earlier >= 0.98 for earlier, later in zip(starts, starts[2:]))


def test_parallel_fetch_threads_share_one_byte_budget():
    import threading

    from app.connectors.website import _ByteBudget

    budget = _ByteBudget(limit=10_000, used=0)
    accepted = []
    refused = []
    lock = threading.Lock()

    def worker():
        for _ in range(10):
            try:
                budget.consume(1_500)
            except ConnectorFailure as exc:
                with lock:
                    refused.append(exc.issue.code)
                return
            with lock:
                accepted.append(1_500)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert budget.used() == sum(accepted) == 9_000
    assert set(refused) == {"total_bytes_exceeded"}


def test_parallel_requests_do_not_refuse_pages_before_the_budget_is_used():
    """Reserving the per-page maximum per request refused pages far too early."""
    pages = 12
    responses = {"https://public.example/robots.txt": (404, {}, b"")}
    links = "".join(f"<a href='/p{n}'>p</a>" for n in range(pages))
    responses["https://public.example/"] = (200, HTML, f"<main>{links}</main>".encode())
    for n in range(pages):
        responses[f"https://public.example/p{n}"] = (200, HTML, page_body(f"Page {n}"))
    value = config(max_pages=pages + 1, max_depth=1)
    # Four parallel fetches; the total allows about three per-page maximums.
    resolved = policy(
        value,
        fetch_concurrency=4,
        max_response_bytes=100_000,
        max_total_bytes=350_000,
    )
    outcomes = connector_for(TransportDouble(responses)).discover_all(value, resolved)
    assert [item.status for item in outcomes].count("included") == pages + 1
    assert not [item for item in outcomes if item.status == "failed"]


ARTICLE = (
    "<main><h1>Guide</h1><p>"
    + "This guide explains how the product handles duplicate pages. " * 6
    + "</p></main>"
).encode()


def duplicate_site():
    canonical_page = (
        b"<html><head><link rel='canonical' href='/a?utm_source=feed'></head>"
        b"<body><main><p>A copy of the guide.</p></main></body></html>"
    )
    outside = (
        b"<html><head><link rel='canonical' href='https://other.example/c'></head>"
        b"<body><main><p>Page C stands alone.</p></main></body></html>"
    )
    return {
        "https://public.example/robots.txt": (404, {}, b""),
        "https://public.example/a": (200, HTML, ARTICLE),
        "https://public.example/a/": (200, HTML, ARTICLE),
        "https://public.example/b": (200, HTML, canonical_page),
        "https://public.example/c": (200, HTML, outside),
    }


DUPLICATE_URLS = [
    "https://public.example/a",
    "https://public.example/a/",
    "https://public.example/a?utm_source=x&page=2&fbclid=1",
    "https://public.example/a?utm_source=x",
    "https://public.example/b",
    "https://public.example/c",
]


def test_tracking_parameters_canonical_links_and_content_produce_one_page():
    responses = duplicate_site()
    responses["https://public.example/a?page=2"] = (200, HTML, ARTICLE)
    transport = TransportDouble(responses)
    value = config(selection={"mode": "url_list", "urls": DUPLICATE_URLS})
    outcomes = connector_for(transport).discover_all(value, policy(value))
    by_status = {}
    for item in outcomes:
        by_status.setdefault(item.status, []).append(item)
    assert [item.canonical_location for item in by_status["included"]] == [
        "https://public.example/a",
        "https://public.example/c",
    ]
    reasons = {item.external_id: item.reason for item in by_status["duplicate"]}
    # The same path with a different real parameter is a different URL whose
    # content matches, so it is a content duplicate that names the retained page.
    assert (
        "Same content as https://public.example/a"
        in reasons["https://public.example/a?page=2"]
    )
    assert (
        "Same content as https://public.example/a"
        in reasons["https://public.example/a/"]
    )
    assert (
        "Tracking parameters were removed"
        in reasons["https://public.example/a?utm_source=x"]
    )
    assert (
        "Declares https://public.example/a as its canonical URL"
        in reasons["https://public.example/b"]
    )
    included_c = by_status["included"][1]
    assert "Ignored rel=canonical https://other.example/c" in included_c.reason
    fetched = [call[0] for call in transport.calls]
    assert "https://public.example/a?utm_source=x" not in fetched
    assert "https://other.example/c" not in fetched


def test_canonical_target_keeps_the_depth_of_the_page_that_declares_it():
    """Like docs.python.org: /docs/ links to and declares /docs/index.html."""
    start = (
        b"<html><head><link rel='canonical' href='/docs/index.html'></head>"
        b"<body><main><a href='index.html'>Contents</a></main></body></html>"
    )
    index = b"<main><a href='/docs/guide.html'>Guide</a>" + ARTICLE + b"</main>"
    transport = TransportDouble(
        {
            "https://public.example/robots.txt": (404, {}, b""),
            "https://public.example/docs/": (200, HTML, start),
            "https://public.example/docs/index.html": (200, HTML, index),
            "https://public.example/docs/guide.html": (200, HTML, page_body("Guide")),
        }
    )
    value = config(
        selection={"mode": "crawl", "start_url": "https://public.example/docs/"},
        max_depth=1,
    )
    outcomes = connector_for(transport).discover_all(value, policy(value))
    assert [
        item.canonical_location for item in outcomes if item.status == "included"
    ] == [
        "https://public.example/docs/index.html",
        "https://public.example/docs/guide.html",
    ]


def test_out_of_scope_navigation_links_do_not_use_up_the_page_limit():
    navigation = "".join(
        f"<a href='https://other.example/{n}'>x</a>" for n in range(40)
    )
    pages = "".join(f"<a href='/docs/p{n}.html'>p</a>" for n in range(3))
    responses = {
        "https://public.example/robots.txt": (404, {}, b""),
        "https://public.example/docs/": (
            200,
            HTML,
            f"<nav>{navigation}</nav><main>{pages}</main>".encode(),
        ),
    }
    for n in range(3):
        responses[f"https://public.example/docs/p{n}.html"] = (
            200,
            HTML,
            page_body(f"Page {n}"),
        )
    value = config(
        selection={"mode": "crawl", "start_url": "https://public.example/docs/"},
        max_pages=4,
        max_depth=1,
    )
    outcomes = connector_for(TransportDouble(responses)).discover_all(
        value, policy(value)
    )
    assert len([item for item in outcomes if item.status == "included"]) == 4
    excluded = [item for item in outcomes if item.status == "excluded"]
    # Out-of-scope links are listed up to max_pages * 4, then dropped silently.
    assert len(excluded) == 16 - 1
    assert all("allowlist" in item.reason for item in excluded)


def test_oversized_page_fails_with_a_message_that_says_how_to_proceed():
    """A page is never dropped silently; the run fails and names the fix."""
    start = b"<main><a href='/big.html'>Big</a><a href='/ok.html'>Ok</a></main>"
    big = b"<main>" + b"x" * (settings.website_max_response_bytes + 10) + b"</main>"
    responses = {
        "https://public.example/robots.txt": (404, {}, b""),
        "https://public.example/": (200, HTML, start),
        "https://public.example/big.html": (200, HTML, big),
        "https://public.example/ok.html": (200, HTML, page_body("Ok")),
    }
    value = config()
    outcomes = connector_for(TransportDouble(responses)).discover_all(
        value, policy(value)
    )
    by_url = {item.canonical_location: item for item in outcomes}
    assert by_url["https://public.example/ok.html"].status == "included"
    big_page = by_url["https://public.example/big.html"]
    assert (big_page.status, big_page.error_code) == ("failed", "response_too_large")
    assert big_page.reason.startswith(
        "The page is larger than the 20 MiB per-page limit."
    )
    assert "Filter pages" in big_page.reason


def test_short_identical_pages_are_not_merged_by_content():
    shell = b"<html><body><div id='app'></div><script>boot()</script></body></html>"
    transport = TransportDouble(
        {
            "https://public.example/robots.txt": (404, {}, b""),
            "https://public.example/one": (200, HTML, shell),
            "https://public.example/two": (200, HTML, shell),
        }
    )
    value = config(
        selection={
            "mode": "url_list",
            "urls": ["https://public.example/one", "https://public.example/two"],
        }
    )
    outcomes = connector_for(transport).discover_all(value, policy(value))
    assert [item.status for item in outcomes] == ["included", "included"]


# Fixes from the 2026-10-03 review. Each test reproduces a confirmed finding.

LONG_TEXT = "Readable documentation text. " * 12


def site(pages, robots=(404, {}, b"")):
    responses = {"https://public.example/robots.txt": robots}
    responses.update(pages)
    return TransportDouble(responses)


def test_non_http_links_are_ignored_and_never_fail_the_crawl():
    page = (
        "<main><a href='mailto:team@example.com'>Mail</a>"
        "<a href='tel:+15550100'>Call</a><a href='javascript:void(0)'>Menu</a>"
        "<a href='mailto:team@example.com'>Mail again</a>"
        "<a href='http://exa mple.com:99999/'>Broken</a>"
        "<a href='http://exa mple.com:99999/'>Broken again</a>"
        f"<p>{LONG_TEXT}</p></main>"
    ).encode()
    outcomes = connector_for(
        site({"https://public.example/": (200, HTML, page)})
    ).discover_all(config(), policy(config()))
    assert not [item for item in outcomes if item.status == "failed"]
    assert not [
        item
        for item in outcomes
        if any(
            scheme in (item.reason + str(item.external_id))
            for scheme in ("mailto", "tel:")
        )
    ]
    broken = [item for item in outcomes if "link was skipped" in item.reason]
    assert len(broken) == 1 and broken[0].status == "excluded"


def test_overlong_urls_are_excluded_once_with_bounded_keys():
    long_path = "/a" * 1500
    page = (
        f"<main><a href='{long_path}'>x</a><a href='{long_path}'>x</a>"
        f"<p>{LONG_TEXT}</p></main>"
    ).encode()
    outcomes = connector_for(
        site({"https://public.example/": (200, HTML, page)})
    ).discover_all(config(), policy(config()))
    long_items = [item for item in outcomes if "longer than" in item.reason]
    assert len(long_items) == 1
    assert long_items[0].status == "excluded"
    assert len(long_items[0].canonical_location.encode()) <= website.MAX_URL_BYTES
    assert not [item for item in outcomes if item.status == "failed"]


def test_canonical_naming_the_url_before_a_redirect_keeps_the_page():
    body = (
        "<html><head><link rel='canonical' href='https://public.example/a'></head>"
        f"<body><main><p>{LONG_TEXT}</p></main></body></html>"
    ).encode()
    value = config(selection={"mode": "single_url", "url": "https://public.example/a"})
    outcomes = connector_for(
        site(
            {
                "https://public.example/a": (
                    301,
                    {"location": "https://public.example/a/"},
                    b"",
                ),
                "https://public.example/a/": (200, HTML, body),
            }
        )
    ).discover_all(value, policy(value))
    assert [item.status for item in outcomes] == ["included"]


def test_pages_naming_each_other_as_canonical_index_one_of_them():
    def page(target, text):
        return (
            f"<html><head><link rel='canonical' href='{target}'></head><body>"
            f"<main><p>{text} {LONG_TEXT}</p></main></body></html>"
        ).encode()

    value = config(
        selection={
            "mode": "url_list",
            "urls": ["https://public.example/a", "https://public.example/b"],
        }
    )
    outcomes = connector_for(
        site(
            {
                "https://public.example/a": (200, HTML, page("/b", "A")),
                "https://public.example/b": (200, HTML, page("/a", "B")),
            }
        )
    ).discover_all(value, policy(value))
    included = [item for item in outcomes if item.status == "included"]
    assert [item.canonical_location for item in included] == [
        "https://public.example/b"
    ]
    assert "that page is not indexed" in included[0].reason


def test_canonical_target_is_admitted_past_the_discovery_limit():
    links = "".join(f"<a href='/x{n}'>x</a>" for n in range(20))
    start = f"<main><a href='/b'>b</a>{links}<p>{LONG_TEXT}</p></main>".encode()
    declares = (
        "<html><head><link rel='canonical' href='/c'></head>"
        f"<body><main><p>B {LONG_TEXT}</p></main></body></html>"
    ).encode()
    pages = {
        "https://public.example/": (200, HTML, start),
        "https://public.example/b": (200, HTML, declares),
        "https://public.example/c": (200, HTML, page_body(f"C {LONG_TEXT}")),
    }
    value = config(max_pages=2, max_depth=1)
    outcomes = connector_for(site(pages)).discover_all(value, policy(value))
    assert "https://public.example/c" in [
        item.canonical_location for item in outcomes if item.status == "included"
    ]
    assert any("Additional URLs were omitted" in item.reason for item in outcomes)


def test_strip_tracking_keeps_other_parameters_exactly():
    assert strip_tracking("https://x.example/p?sort=name:asc") == (
        "https://x.example/p?sort=name:asc"
    )
    assert strip_tracking("https://x.example/p?q=a%20b&utm_source=x&b=2") == (
        "https://x.example/p?q=a%20b&b=2"
    )
    assert strip_tracking("https://x.example/p?utm_medium=a&fbclid=1") == (
        "https://x.example/p"
    )


def test_path_filters_apply_only_to_crawl_and_sitemap_modes():
    pages = {"https://public.example/blog/x": (200, HTML, page_body(LONG_TEXT))}
    listed = config(
        selection={"mode": "url_list", "urls": ["https://public.example/blog/x"]},
        include_path_prefixes=["/docs/"],
    )
    outcomes = connector_for(site(pages)).discover_all(listed, policy(listed))
    assert [item.status for item in outcomes] == ["included"]
    crawled = config(
        selection={"mode": "crawl", "start_url": "https://public.example/blog/x"},
        include_path_prefixes=["/docs/"],
    )
    outcomes = connector_for(site(pages)).discover_all(crawled, policy(crawled))
    assert [item.status for item in outcomes] == ["excluded"]


def test_url_list_limit_is_checked_with_the_default_maximum_pages():
    with pytest.raises(ValidationError) as caught:
        WebsiteConfig.model_validate(
            {
                "kind": "website",
                "selection": {
                    "mode": "url_list",
                    "urls": [f"https://x.example/{n}" for n in range(60)],
                },
                "allowed_origins": ["https://x.example"],
            }
        )
    assert caught.value.errors()[0]["loc"] == ("max_pages",)


def test_date_only_lastmod_does_not_skip_a_page_changed_later_that_day():
    sitemap = b"""<urlset>
      <url><loc>https://public.example/today</loc><lastmod>2026-10-02</lastmod></url>
    </urlset>"""
    transport = site(
        {
            "https://public.example/sitemap.xml": (
                200,
                {"content-type": "application/xml"},
                sitemap,
            ),
            "https://public.example/today": (200, HTML, page_body("Changed")),
        }
    )
    stored = datetime(2026, 10, 2, 10, tzinfo=timezone.utc)
    priors = {
        "https://public.example/today": PriorWebsiteRevision(
            content=page_body("Stored"), media_type="text/html", fetched_at=stored
        )
    }
    value = config(
        selection={
            "mode": "sitemap",
            "sitemap_url": "https://public.example/sitemap.xml",
        }
    )
    connector_for(transport).fetch_all(value, policy(value), priors)
    assert "https://public.example/today" in [call[0] for call in transport.calls]


def test_queued_pages_fail_at_the_deadline_without_sleeping_past_it():
    clock = FakeClock()
    robots = (200, {"content-type": "text/plain"}, b"User-agent: *\nCrawl-delay: 10\n")
    urls = [f"https://public.example/p{n}" for n in range(30)]
    pages = {url: (200, HTML, page_body(url)) for url in urls}
    value = config(selection={"mode": "url_list", "urls": urls}, max_pages=30)
    resolved = policy(value)
    outcomes = connector_for(site(pages, robots), clock).discover_all(value, resolved)
    assert sum(clock.sleeps) < resolved.deadline_seconds
    failed = [item for item in outcomes if item.status == "failed"]
    assert failed and all(item.error_code == "deadline_exceeded" for item in failed)
    assert len(outcomes) == len(urls)


def test_redirect_hops_keep_the_rate_and_robots_rules_of_their_target():
    clock = FakeClock()
    robots = (
        200,
        {"content-type": "text/plain"},
        b"User-agent: *\nDisallow: /private\n",
    )
    transport = site(
        {
            "https://public.example/a": (301, {"location": "/b"}, b""),
            "https://public.example/b": (200, HTML, page_body(LONG_TEXT)),
            "https://public.example/c": (301, {"location": "/private/x"}, b""),
            "https://public.example/private/x": (200, HTML, page_body("secret")),
        },
        robots,
    )
    value = config(
        selection={
            "mode": "url_list",
            "urls": ["https://public.example/a", "https://public.example/c"],
        },
        requests_per_second=1,
    )
    outcomes = connector_for(transport, clock).discover_all(value, policy(value))
    by_url = {item.external_id: item for item in outcomes}
    assert by_url["https://public.example/b"].status == "included"
    assert by_url["https://public.example/c"].status == "excluded"
    assert "robots.txt disallows the redirect target" in (
        by_url["https://public.example/c"].reason
    )
    assert "https://public.example/private/x" not in [
        call[0] for call in transport.calls
    ]
    # robots.txt, /a, the hop to /b and /c are each spaced by one second.
    assert clock.sleeps.count(1.0) >= 3


class SlowFirstTransport(TransportDouble):
    """The first page answers last, so arrival order differs from queue order."""

    def request(self, url, address, timeout, headers, max_bytes):
        if url.endswith("/one"):
            time.sleep(0.3)
        return super().request(url, address, timeout, headers, max_bytes)


def test_identical_pages_keep_the_first_queued_one_whatever_answers_first():
    body = page_body(LONG_TEXT)
    urls = ["https://public.example/one", "https://public.example/two"]
    transport = SlowFirstTransport(
        {
            "https://public.example/robots.txt": (404, {}, b""),
            urls[0]: (200, HTML, body),
            urls[1]: (200, HTML, body),
        }
    )
    value = config(selection={"mode": "url_list", "urls": urls}, requests_per_second=5)
    outcomes = connector_for(transport).discover_all(
        value, policy(value, fetch_concurrency=2)
    )
    assert [(item.canonical_location, item.status) for item in outcomes] == [
        (urls[0], "included"),
        (urls[1], "duplicate"),
    ]


def test_truncated_response_is_not_accepted_as_a_complete_page():
    listener = socket.create_server(("127.0.0.1", 0))
    port = listener.getsockname()[1]

    def serve():
        connection, _ = listener.accept()
        with connection:
            connection.recv(4096)
            connection.sendall(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
                b"Content-Length: 100\r\nConnection: close\r\n\r\nonly part"
            )

    threading.Thread(target=serve, daemon=True).start()
    try:
        with pytest.raises(ConnectorFailure) as raised:
            StdlibTransport().request(
                f"http://example.test:{port}/",
                "127.0.0.1",
                5,
                {"Host": f"example.test:{port}", "Connection": "close"},
                1024 * 1024,
            )
    finally:
        listener.close()
    assert raised.value.issue.code == "truncated_response"
    assert raised.value.issue.retryable is True


def test_retries_cover_502_504_and_timeouts():
    clock = FakeClock()
    transport = SequenceTransport(
        {
            "https://public.example/robots.txt": NO_ROBOTS,
            "https://public.example/a": [(502, {}, b""), (200, HTML, page_body("A"))],
            "https://public.example/b": [(504, {}, b""), (200, HTML, page_body("B"))],
            "https://public.example/c": [
                ConnectorFailure(
                    ConnectorIssue(
                        code="request_timeout", message="timed out", retryable=True
                    )
                ),
                (200, HTML, page_body("C")),
            ],
        }
    )
    urls = [f"https://public.example/{name}" for name in "abc"]
    value = config(selection={"mode": "url_list", "urls": urls})
    outcomes = connector_for(transport, clock).discover_all(value, policy(value))
    assert [(item.status, item.attempts) for item in outcomes] == [("included", 2)] * 3
    # Backoff starts at the base delay (jitter is zero in these tests).
    assert clock.sleeps.count(settings.website_retry_base_delay_seconds) >= 3


def test_entity_hidden_inside_a_gzip_sitemap_is_rejected():
    body = gzip.compress(b"<!DOCTYPE x [<!ENTITY a 'b'>]><urlset></urlset>")
    transport = site(
        {
            "https://public.example/sitemap.xml.gz": (
                200,
                {"content-type": "application/gzip"},
                body,
            )
        }
    )
    value = config(
        selection={
            "mode": "sitemap",
            "sitemap_url": "https://public.example/sitemap.xml.gz",
        }
    )
    with pytest.raises(ConnectorFailure) as caught:
        connector_for(transport).discover_all(value, policy(value))
    assert caught.value.issue.code == "unsafe_sitemap"


def test_sitemap_index_follows_at_most_fifty_nested_sitemaps():
    nested = [f"https://public.example/s{n}.xml" for n in range(55)]
    index = (
        "<sitemapindex>"
        + "".join(f"<sitemap><loc>{url}</loc></sitemap>" for url in nested)
        + "</sitemapindex>"
    ).encode()
    xml = {"content-type": "application/xml"}
    pages = {"https://public.example/index.xml": (200, xml, index)}
    for url in nested:
        pages[url] = (200, xml, b"<urlset></urlset>")
    transport = site(pages)
    value = config(
        selection={"mode": "sitemap", "sitemap_url": "https://public.example/index.xml"}
    )
    outcomes = connector_for(transport).discover_all(value, policy(value))
    fetched = [call[0] for call in transport.calls if "/s" in call[0]]
    assert len(fetched) == website.MAX_NESTED_SITEMAPS
    assert any(
        "5 more nested sitemaps were omitted" in item.reason for item in outcomes
    )


def test_canonical_target_already_queued_is_fetched_before_the_page_limit():
    links = "".join(f"<a href='/{name}'>{name}</a>" for name in ("a", "b", "c", "t"))
    declares = (
        "<html><head><link rel='canonical' href='/t'></head>"
        f"<body><main><p>A {LONG_TEXT}</p></main></body></html>"
    ).encode()
    pages = {
        "https://public.example/": (200, HTML, f"<main>{links}</main>".encode()),
        "https://public.example/a": (200, HTML, declares),
        "https://public.example/b": (200, HTML, page_body(f"B {LONG_TEXT}")),
        "https://public.example/c": (200, HTML, page_body(f"C {LONG_TEXT}")),
        "https://public.example/t": (200, HTML, page_body(f"T {LONG_TEXT}")),
    }
    value = config(max_pages=3, max_depth=1)
    outcomes = connector_for(site(pages)).discover_all(value, policy(value))
    by_url = {item.canonical_location: item.status for item in outcomes}
    assert by_url["https://public.example/t"] == "included"
    assert by_url["https://public.example/a"] == "duplicate"
    assert by_url["https://public.example/c"] == "excluded"


def test_page_is_indexed_when_its_canonical_target_fails():
    declares = (
        "<html><head><link rel='canonical' href='/t'></head>"
        f"<body><main><p>A {LONG_TEXT}</p></main></body></html>"
    ).encode()
    value = config(
        selection={
            "mode": "url_list",
            "urls": ["https://public.example/a", "https://public.example/t"],
        }
    )
    outcomes, artifacts = connector_for(
        site(
            {
                "https://public.example/a": (200, HTML, declares),
                "https://public.example/t": (404, HTML, b"gone"),
            }
        )
    ).fetch_all(value, policy(value))
    by_url = {item.canonical_location: item for item in outcomes}
    assert by_url["https://public.example/t"].status == "failed"
    page = by_url["https://public.example/a"]
    assert page.status == "included"
    assert "that page is not indexed" in page.reason
    assert [artifact.canonical_location for artifact in artifacts] == [
        "https://public.example/a"
    ]
    # One outcome per URL: the earlier duplicate entry was replaced, not added.
    assert len(outcomes) == 2


def test_relative_sitemap_locations_are_excluded_with_a_reason():
    sitemap = b"<urlset><url><loc>/relative</loc></url></urlset>"
    transport = site(
        {
            "https://public.example/sitemap.xml": (
                200,
                {"content-type": "application/xml"},
                sitemap,
            )
        }
    )
    value = config(
        selection={
            "mode": "sitemap",
            "sitemap_url": "https://public.example/sitemap.xml",
        }
    )
    outcomes = connector_for(transport).discover_all(value, policy(value))
    assert [(item.status, item.reason) for item in outcomes] == [
        ("excluded", "The URL is not absolute. The link was skipped.")
    ]
