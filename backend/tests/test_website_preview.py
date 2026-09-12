import time
from uuid import UUID
from urllib.parse import urlsplit

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors.base import ConnectorFailure, ConnectorIssue
from app.connectors.safe_http import SafeHttpClient, canonical_url, resolve_public
from app.connectors.website import WebsiteConnector
from app.core.config import settings
from app.models.document import ProcessingRun
from app.models.index import IndexVersion
from app.models.preview import SourcePreview
from app.providers import embeddings
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
        "max_response_bytes": 20_000,
        "max_total_bytes": 100_000,
        "request_timeout_seconds": 2,
        "deadline_seconds": 10,
        "concurrency": 2,
        "requests_per_second": 20,
        "redirect_limit": 2,
        "user_agent": "RAG-Quality-Studio-Test/1",
        "respect_robots": True,
    }
    value.update(overrides)
    return value


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
    outcomes = connector.discover_all(
        config(selection={"mode": "single_url", "url": "https://public.example/"})
    )
    assert len(outcomes) == 1
    assert outcomes[0].status == "failed"
    assert outcomes[0].error_code == "request_timeout"
    assert outcomes[0].reason == "The website request timed out."


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
    outcomes = connector.discover_all(config())
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
        connector.discover_all(value)
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
