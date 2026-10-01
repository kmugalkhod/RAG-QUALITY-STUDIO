"""Organization chat model approvals: catalog parsing, roles, isolation and use."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.core.auth import Principal, current_principal
from app.core.config import settings
from app.db.session import get_session
from app.main import app
from app.models.project import Project
from app.providers import chat_models as chat_model_context
from app.providers import credentials, generation
from app.services import chat_models, pipelines, provider_credentials

ROUTE = "/api/organizations/current/chat-models"
CATALOG = [
    chat_models.CatalogModel(
        "openai/gpt-4.1-mini", "GPT-4.1 Mini", 1_047_576, Decimal("0.4"), Decimal("1.6")
    ),
    chat_models.CatalogModel(
        "anthropic/claude-haiku-4.5", "Claude Haiku 4.5", 200_000, None, None
    ),
    chat_models.CatalogModel("tiny/model", "Tiny", 4096, Decimal("0"), Decimal("0")),
]


def admin(org="org_a"):
    return Principal(uuid4(), f"user_admin_{org}", None, "clerk", org, "org:admin")


def member(org="org_a"):
    return Principal(uuid4(), f"user_member_{org}", None, "clerk", org, "org:member")


@pytest.fixture
def org_models(database, monkeypatch):
    """Clerk mode, two organizations, a stubbed catalog and an environment key."""
    engine, _ = database
    monkeypatch.setattr(settings, "auth_mode", "clerk")
    monkeypatch.setattr(settings, "chat_model", "")
    monkeypatch.setattr(settings, "chat_models", [])
    monkeypatch.setattr(settings, "chat_context_tokens", 32_000)
    monkeypatch.setattr(settings, "chat_max_tokens", 1024)
    fetched = datetime(2026, 10, 1, tzinfo=UTC)
    monkeypatch.setattr(
        chat_models, "catalog", lambda transport=None, refresh=False: (CATALOG, fetched)
    )
    # Bind a usable key without touching encrypted storage.
    monkeypatch.setattr(
        provider_credentials,
        "resolve",
        lambda session, project_id: (
            credentials.ProviderCredential(SecretStr("k" * 30), None, "test"),
            "",
        ),
    )
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        a = Project(name="A", organization_id="org_a")
        b = Project(name="B", organization_id="org_b")
        session.add_all([a, b])
        session.commit()

        def override_session():
            yield session

        principal = {"value": admin()}
        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[current_principal] = lambda: principal["value"]
        try:
            with TestClient(app) as client:
                yield client, session, principal, a, b
        finally:
            app.dependency_overrides.clear()
            session.close()
            transaction.rollback()


def test_parse_catalog_keeps_only_current_text_chat_models():
    future = (datetime.now(UTC) + timedelta(days=30)).date().isoformat()
    payload = {
        "data": [
            {
                "id": "openai/gpt-4.1-mini",
                "name": "GPT-4.1 Mini",
                "context_length": 128000,
                "architecture": {"output_modalities": ["text"]},
                "pricing": {"prompt": "0.0000004", "completion": "0.0000016"},
                "expiration_date": future,
            },
            {
                "id": "openrouter/auto",
                "context_length": 2_000_000,
                "pricing": {"prompt": "-1"},
            },
            {
                "id": "image/model",
                "context_length": 8192,
                "architecture": {"output_modalities": ["image"]},
            },
            {"id": "openai/text-embedding-3-small", "context_length": 8192},
            {
                "id": "old/model",
                "context_length": 8192,
                "expiration_date": "2020-01-01",
            },
            {"id": "small/model", "context_length": 1024},
            {"id": "bad id with spaces", "context_length": 8192},
            {"id": "flag/model", "context_length": True},
            "not an object",
        ]
    }
    models = {m.id: m for m in chat_models.parse_catalog(payload)}
    assert set(models) == {"openai/gpt-4.1-mini", "openrouter/auto"}
    mini = models["openai/gpt-4.1-mini"]
    assert mini.prompt_usd_per_mtok == Decimal("0.4")
    assert mini.completion_usd_per_mtok == Decimal("1.6")
    auto = models["openrouter/auto"]
    assert auto.name == "openrouter/auto"
    assert auto.prompt_usd_per_mtok is None and auto.completion_usd_per_mtok is None


def test_catalog_fetch_is_bounded_and_failures_are_safe(monkeypatch):
    chat_models.clear_catalog_cache()
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200, json={"data": [{"id": "a/b", "context_length": 4096}]}
        )

    models, _ = chat_models.catalog(httpx.MockTransport(handler), refresh=True)
    assert [m.id for m in models] == ["a/b"]
    assert "authorization" not in seen[0].headers
    assert seen[0].url.params["output_modalities"] == "text"
    # A cached catalog is reused without another request.
    chat_models.catalog(httpx.MockTransport(handler))
    assert len(seen) == 1
    with pytest.raises(HTTPException) as failed:
        chat_models.catalog(
            httpx.MockTransport(lambda request: httpx.Response(500)), refresh=True
        )
    assert failed.value.status_code == 503
    monkeypatch.setattr(chat_models, "CATALOG_MAX_BYTES", 10)
    with pytest.raises(HTTPException):
        chat_models.catalog(httpx.MockTransport(handler), refresh=True)
    chat_models.clear_catalog_cache()


def test_admin_approves_and_first_approval_is_default(org_models):
    client, _, _, _, _ = org_models
    response = client.post(ROUTE, json={"model_id": "anthropic/claude-haiku-4.5"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["default_model"] == "anthropic/claude-haiku-4.5"
    [model] = body["models"]
    assert model["source"] == "organization"
    assert model["context_tokens"] == 32_000  # capped by CHAT_CONTEXT_TOKENS
    assert model["prompt_usd_per_mtok"] is None  # unknown price stays unknown
    again = client.post(ROUTE, json={"model_id": "anthropic/claude-haiku-4.5"})
    assert len(again.json()["models"]) == 1
    second = client.post(ROUTE, json={"model_id": "openai/gpt-4.1-mini"}).json()
    assert second["default_model"] == "anthropic/claude-haiku-4.5"
    switched = client.put(ROUTE + "/default", json={"model_id": "openai/gpt-4.1-mini"})
    assert switched.json()["default_model"] == "openai/gpt-4.1-mini"
    assert [m["is_default"] for m in switched.json()["models"]].count(True) == 1


def test_unknown_models_are_rejected(org_models):
    client, _, _, _, _ = org_models
    assert client.post(ROUTE, json={"model_id": "made/up"}).status_code == 422
    assert client.post(ROUTE, json={"model_id": "bad id"}).status_code == 422
    assert (
        client.put(ROUTE + "/default", json={"model_id": "made/up"}).status_code == 404
    )


def test_members_can_read_but_not_change(org_models):
    client, _, principal, _, _ = org_models
    client.post(ROUTE, json={"model_id": "openai/gpt-4.1-mini"})
    principal["value"] = member()
    read = client.get(ROUTE)
    assert read.status_code == 200
    assert read.json()["can_manage"] is False
    assert [m["id"] for m in read.json()["models"]] == ["openai/gpt-4.1-mini"]
    assert client.get(ROUTE + "/catalog").status_code == 403
    assert client.post(ROUTE, json={"model_id": "tiny/model"}).status_code == 403
    assert (
        client.post(
            ROUTE + "/remove", json={"model_id": "openai/gpt-4.1-mini"}
        ).status_code
        == 403
    )


def test_catalog_search_marks_approved_models(org_models):
    client, _, _, _, _ = org_models
    client.post(ROUTE, json={"model_id": "openai/gpt-4.1-mini"})
    page = client.get(ROUTE + "/catalog", params={"q": "gpt mini"}).json()
    assert page["total"] == 1
    assert page["items"][0]["approved"] is True
    paged = client.get(ROUTE + "/catalog", params={"limit": 1, "offset": 1}).json()
    assert paged["total"] == 3 and len(paged["items"]) == 1


def test_organizations_are_isolated(org_models):
    client, session, principal, a, b = org_models
    client.post(ROUTE, json={"model_id": "openai/gpt-4.1-mini"})
    principal["value"] = admin("org_b")
    assert client.get(ROUTE).json()["models"] == []
    with provider_credentials.bound_for_project(session, b.id):
        with pytest.raises(generation.GenerationError) as missing:
            generation.configured("openai/gpt-4.1-mini")
    assert missing.value.code == "no_models"
    with provider_credentials.bound_for_project(session, a.id):
        assert generation.configured()["model"] == "openai/gpt-4.1-mini"


def test_generation_uses_approval_context_and_blocks_removed_models(org_models):
    client, session, _, a, _ = org_models
    client.post(ROUTE, json={"model_id": "tiny/model"})
    with provider_credentials.bound_for_project(session, a.id):
        config = generation.configured("tiny/model", 2048)
        assert config["context_tokens"] == 4096
        with pytest.raises(generation.GenerationError, match="context budget"):
            generation.configured("tiny/model", 3500)
    client.post(ROUTE + "/remove", json={"model_id": "tiny/model"})
    assert (
        client.post(ROUTE + "/remove", json={"model_id": "tiny/model"}).status_code
        == 404
    )
    with provider_credentials.bound_for_project(session, a.id):
        with pytest.raises(generation.GenerationError):
            generation.configured("tiny/model", 2048)


def test_server_models_remain_available_next_to_approvals(org_models, monkeypatch):
    client, session, principal, a, _ = org_models
    monkeypatch.setattr(settings, "chat_model", "server/default")
    monkeypatch.setattr(settings, "chat_models", ["server/extra", "x/text-embedding-1"])
    before = pipelines.options(session, a.id, principal["value"])
    assert before["models"] == ["server/default", "server/extra"]
    assert before["default_model"] == "server/default"
    assert before["error"] is None and before["can_manage_models"] is True
    client.post(ROUTE, json={"model_id": "openai/gpt-4.1-mini"})
    after = pipelines.options(session, a.id, member())
    assert after["models"] == ["openai/gpt-4.1-mini", "server/default", "server/extra"]
    # An organization default outranks the server default.
    assert after["default_model"] == "openai/gpt-4.1-mini"
    assert after["model_options"][1]["source"] == "server"
    assert after["can_manage_models"] is False


def test_options_report_why_answers_are_unavailable(org_models, monkeypatch):
    _, session, principal, a, _ = org_models
    empty = pipelines.options(session, a.id, principal["value"])
    assert empty["models"] == [] and empty["default_model"] is None
    assert empty["error_code"] == "no_models"
    assert "organization admin" in empty["error"]
    monkeypatch.setattr(settings, "chat_model", "server/default")
    monkeypatch.setattr(
        provider_credentials,
        "resolve",
        lambda session, project_id: (None, credentials.MISSING_ORGANIZATION),
    )
    missing = pipelines.options(session, a.id, principal["value"])
    assert missing["models"] == ["server/default"]
    assert missing["error_code"] == "provider_key"


def test_unbound_context_uses_server_models_only(monkeypatch):
    monkeypatch.setattr(settings, "chat_model", "server/default")
    monkeypatch.setattr(settings, "chat_models", [])
    assert [m.id for m in chat_model_context.available()] == ["server/default"]
