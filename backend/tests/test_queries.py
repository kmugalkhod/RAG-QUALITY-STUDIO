from uuid import UUID, uuid4
from unittest.mock import patch
import httpx
import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.query import QueryRun
from app.providers import generation
from app.pipelines.generation import build_context, prompt_bound, validate_citations
from app.workers.indexing import process_index
from test_indexes import index_api, embedding_config, prepared, create  # noqa: F401
from test_documents import documents_api  # noqa: F401


@pytest.fixture
def query_api(index_api, monkeypatch):  # noqa: F811
    client, engine, p, q, _ = index_api
    monkeypatch.setattr(settings, "chat_model", "test/chat")
    prepared(client, engine, p)
    index = create(client, p)
    process_index(UUID(index["id"]), engine)
    yield client, engine, p, q, index
    with Session(engine) as session:
        session.execute(
            delete(QueryRun).where(QueryRun.project_id.in_([UUID(p), UUID(q)]))
        )
        session.commit()


def ask(client, p, index, **extra):
    return client.post(
        f"/api/projects/{p}/query-runs",
        json={"index_id": index["id"], "question": "abcd?", "top_k": 2, **extra},
    )


def test_persistence_citations_scope(query_api):
    c, engine, p, q, index = query_api
    with patch.object(
        generation.OpenRouterChat,
        "generate",
        return_value=generation.Completion(
            "Answer [S1] and [S99]", "test/chat", {"total_tokens": 22}, None
        ),
    ) as provider:
        response = ask(c, p, index)
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["status"] == "succeeded"
    s = run["snapshot"]
    assert s["citations"]["valid"] == ["S1"] and s["citations"]["invalid"] == ["S99"]
    assert s["evidence"][0]["text"] == "abcd"
    assert s["messages"] == provider.call_args.args[0]
    assert s["cost_usd"] is None and s["usage"]["total_tokens"] == 22
    assert all(s[k] >= 0 for k in ("retrieval_ms", "generation_ms", "total_ms"))
    assert c.get(f"/api/projects/{p}/query-runs/{run['id']}").json() == run
    assert c.get(f"/api/projects/{q}/query-runs/{run['id']}").status_code == 404
    assert c.get(f"/api/projects/{q}/query-runs").json()["total"] == 0
    assert ask(c, q, index).status_code == 404
    assert ask(c, p, {"id": str(uuid4())}).status_code == 404
    unready = create(c, p)
    assert ask(c, p, unready).status_code == 409


@pytest.mark.parametrize("question,top_k", [(" ", 2), ("a", 0), ("a", 51), ("a", True)])
def test_validation(query_api, question, top_k):
    c, _, p, _, index = query_api
    assert ask(c, p, index, question=question, top_k=top_k).status_code == 422


def test_empty_failure_and_insufficient(query_api):
    c, _, p, _, index = query_api
    with (
        patch("app.services.indexes.retrieve", return_value={"items": []}),
        patch.object(generation.OpenRouterChat, "generate") as provider,
    ):
        run = ask(c, p, index).json()
        assert (
            run["status"] == "insufficient_evidence" and not run["snapshot"]["evidence"]
        )
        provider.assert_not_called()
    for error in [
        generation.GenerationError("OpenRouter timed out."),
        RuntimeError("secret document and key"),
    ]:
        with patch.object(generation.OpenRouterChat, "generate", side_effect=error):
            run = ask(c, p, index).json()
        assert run["status"] == "failed" and "secret" not in run["error"]
        assert run["snapshot"]["evidence"] and run["snapshot"]["generation_ms"] >= 0
    with patch.object(
        generation.OpenRouterChat,
        "generate",
        return_value=generation.Completion(
            "INSUFFICIENT_EVIDENCE: Not in these sources.", "test/chat", None, None
        ),
    ):
        assert ask(c, p, index).json()["status"] == "insufficient_evidence"
    assert c.get(f"/api/projects/{p}/query-runs?limit=1&offset=1").json()["total"] == 4


def test_context_and_references():
    config = dict(context_tokens=2048, max_tokens=512)
    items = [{"rank": 1, "text": "😀" * 1000}, {"rank": 2, "text": "small source"}]
    sources, messages = build_context("question", items, config)
    assert [s["label"] for s in sources] == ["S2"]
    assert prompt_bound(messages) + config["max_tokens"] <= config["context_tokens"]
    with pytest.raises(generation.GenerationError):
        build_context("a" * 2048, [], config)
    with pytest.raises(generation.GenerationError):
        build_context("q", items[:1], config)
    result = validate_citations("A [S2] [S1] [S2, S3]", sources)
    assert result["valid"] == ["S2"] and result["invalid"] == ["S1", "S2, S3"]
    assert validate_citations("Unsupported claim", sources)["missing"]


@pytest.mark.parametrize("status", [401, 402, 403, 429, 500])
def test_safe_provider_errors(monkeypatch, status):
    monkeypatch.setattr(generation, "reserve_request", lambda: None)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(status, text="secret")

    with pytest.raises(generation.GenerationError) as error:
        generation.OpenRouterChat(httpx.MockTransport(respond)).generate(
            [], dict(model="test/chat", max_tokens=128, temperature=0)
        )
    assert "secret" not in str(error.value) and len(calls) == 1


def test_provider_usage_and_output_limits(monkeypatch):
    monkeypatch.setattr(generation, "reserve_request", lambda: None)

    def respond(request):
        return httpx.Response(
            200,
            json={
                "model": "test/chat",
                "choices": [
                    {"finish_reason": "stop", "message": {"content": "Answer [S1]"}}
                ],
                "usage": {"total_tokens": 10, "cost": 0.002},
            },
        )

    result = generation.OpenRouterChat(httpx.MockTransport(respond)).generate(
        [], dict(model="test/chat", max_tokens=128, temperature=0)
    )
    assert result.cost_usd == 0.002 and result.usage == {"total_tokens": 10}


def test_retrieval_failure_configuration_failure_and_stale(query_api, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app.providers.embeddings import EmbeddingError

    c, engine, p, _, index = query_api
    with patch(
        "app.services.indexes.retrieve",
        side_effect=EmbeddingError("Embedding provider unavailable."),
    ):
        run = ask(c, p, index).json()
    assert run["status"] == "failed" and run["snapshot"]["retrieval_ms"] >= 0
    assert run["snapshot"]["generation_ms"] is None
    monkeypatch.setattr(settings, "chat_model", "openai/text-embedding-3-small")
    assert ask(c, p, index).json()["status"] == "failed"
    with Session(engine) as session:
        saved = session.get(QueryRun, UUID(run["id"]))
        saved.status = "running"
        saved.created_at = datetime.now(timezone.utc) - timedelta(minutes=6)
        session.commit()
    recovered = c.get(f"/api/projects/{p}/query-runs/{run['id']}").json()
    assert recovered["status"] == "failed" and "interrupted" in recovered["error"]


def test_truncated_completion_preserves_reported_usage(query_api):
    c, _, p, _, index = query_api
    with patch.object(
        generation.OpenRouterChat,
        "generate",
        return_value=generation.Completion(
            "partial", "test/chat", {"total_tokens": 100}, 0.001, "length"
        ),
    ):
        run = ask(c, p, index).json()
    assert run["status"] == "failed" and run["answer"] is None
    assert run["snapshot"]["usage"] == {"total_tokens": 100}
    assert run["snapshot"]["cost_usd"] == 0.001
