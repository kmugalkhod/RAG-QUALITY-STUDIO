from copy import deepcopy
from uuid import UUID, uuid4
from unittest.mock import patch
import subprocess
import sys

import pytest
from pydantic import ValidationError, SecretStr
from sqlalchemy import text

from app.core.config import settings
from app.providers import embeddings, generation
from app.schemas.index import RetrievalRequest
from app.schemas.pipeline import Execution
from app.schemas.retrieval import HybridSearch
from app.workers.indexing import process_index
from test_documents import documents_api  # noqa: F401
from test_indexes import index_api, embedding_config, prepared, create  # noqa: F401
from test_queries import query_api  # noqa: F401
from test_pipelines import pipeline_api, draft  # noqa: F401
from test_experiments import experiment_api, imported, drive, JudgeDouble  # noqa: F401


def retrieve(c, p, index, retrieval, query="abcd"):
    return c.post(
        f"/api/projects/{p}/retrieval",
        json={"index_id": index["id"], "query": query, "retrieval": retrieval},
    )


@pytest.mark.parametrize(
    "value",
    [
        {"mode": "unknown"},
        {"mode": "keyword", "max_vector_distance": 0.5},
        {"mode": "vector", "max_vector_distance": -0.1},
        {"mode": "vector", "max_vector_distance": 2.1},
        {"mode": "vector", "max_vector_distance": True},
        {"mode": "vector", "top_k": True},
        {"mode": "vector", "top_k": 51},
        {"mode": "vector", "vector_candidates": 50},
        {"mode": "hybrid", "vector_candidates": 201},
        {"mode": "hybrid", "keyword_candidates": 4},
        {"mode": "hybrid", "vector_weight": float("nan")},
        {"mode": "hybrid", "vector_weight": 1.1},
        {"mode": "hybrid", "vector_weight": "0.5"},
    ],
)
def test_retrieval_contract_rejects_invalid_settings(value):
    with pytest.raises(ValidationError):
        RetrievalRequest(index_id=uuid4(), query="q", retrieval=value)


def test_legacy_contract_and_graph_versions():
    request = RetrievalRequest(index_id=uuid4(), query="q", top_k=3)
    assert request.retrieval.mode == "vector" and request.top_k == 3
    with pytest.raises(ValidationError):
        RetrievalRequest(
            index_id=uuid4(), query="q", top_k=3, retrieval={"mode": "keyword"}
        )
    graph = draft(str(uuid4()))["execution"]
    assert Execution.model_validate(graph).model_dump(mode="json") == graph
    graph["schema_version"] = 2
    with pytest.raises(ValidationError):
        Execution.model_validate(graph)
    graph["nodes"][1].pop("top_k")
    graph["nodes"][1]["retrieval"] = {"mode": "keyword", "top_k": 2}
    assert Execution.model_validate(graph).nodes[1].settings.mode == "keyword"


def test_keyword_cutoff_hybrid_order_scope_and_failures(index_api, monkeypatch):  # noqa: F811
    c, engine, p, q, provider = index_api
    _, old_run = prepared(c, engine, p)
    index = create(c, p)
    process_index(UUID(index["id"]), engine)
    # A newer same-project snapshot includes another document; old membership stays fixed.
    prepared(c, engine, p)
    newer = create(c, p)
    process_index(UUID(newer["id"]), engine)
    # Same words in another project must never enter either branch.
    prepared(c, engine, q)
    other = create(c, q)
    process_index(UUID(other["id"]), engine)
    provider.calls.clear()
    lexical = retrieve(c, p, index, {"mode": "keyword", "top_k": 3}).json()
    assert provider.calls == []
    assert [x["text"] for x in lexical["items"]] == ["abcd"]
    assert lexical["items"][0]["cosine_distance"] is None
    assert lexical["items"][0]["lexical_score"] > 0
    assert lexical["items"][0]["run_id"] == old_run["id"]
    assert retrieve(c, q, index, {"mode": "keyword"}).status_code == 404
    vector = retrieve(
        c, p, index, {"mode": "vector", "top_k": 3, "max_vector_distance": 0}
    ).json()
    assert [x["text"] for x in vector["items"]] == ["abcd"]
    assert (
        len(
            retrieve(
                c, p, index, {"mode": "vector", "top_k": 3, "max_vector_distance": 1}
            ).json()["items"]
        )
        == 3
    )
    hybrid = {
        "mode": "hybrid",
        "top_k": 3,
        "vector_candidates": 3,
        "keyword_candidates": 3,
        "vector_weight": 0.5,
    }
    result = retrieve(c, p, index, hybrid, '"abcd" OR "defg"').json()
    # Query embeds to the non-abcd vector: defg is first in vector, second in keyword.
    assert [x["text"] for x in result["items"]] == ["defg", "abcd", "ghij"]
    assert result["items"][0]["fusion_score"] == pytest.approx(0.5 / 61 + 0.5 / 62)
    assert result["diagnostics"]["candidate_count"] == 3
    assert result["items"][1]["fusion_score"] == pytest.approx(0.5 / 63 + 0.5 / 61)
    # Keyword can contribute even if cutoff excludes that chunk in the vector branch.
    cut = retrieve(
        c, p, index, {**hybrid, "max_vector_distance": 0}, '"abcd" OR "defg"'
    ).json()
    abcd = next(x for x in cut["items"] if x["text"] == "abcd")
    assert abcd["vector_rank"] is None and abcd["keyword_rank"] == 1
    assert retrieve(c, p, index, {"mode": "keyword"}, "absent").json()["items"] == []
    with patch.object(
        provider, "embed", side_effect=embeddings.EmbeddingError("Unavailable.")
    ):
        assert retrieve(c, p, index, hybrid).status_code == 503
        assert retrieve(c, p, index, {**hybrid, "vector_weight": 0}).status_code == 200
    # Restore the real credential gate to verify keyword search never enters it.
    monkeypatch.setattr(
        embeddings, "provider_for", lambda _: pytest.fail("Keyword must not embed")
    )
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr(""))
    assert retrieve(c, p, index, {"mode": "keyword"}).status_code == 200
    assert (
        retrieve(c, p, index, {**hybrid, "vector_weight": 0}).json()["diagnostics"][
            "vector_count"
        ]
        == 0
    )
    with engine.connect() as conn:
        assert conn.scalar(
            text("SELECT indexdef FROM pg_indexes WHERE indexname='ix_chunks_lexical'")
        )


def test_v2_saved_preview_and_empty_generation(pipeline_api):  # noqa: F811
    c, _, p, _, index = pipeline_api
    base = f"/api/projects/{p}/pipelines"
    old = c.post(base, json=draft(index["id"])).json()
    payload = draft(index["id"])
    payload["execution"]["schema_version"] = 2
    node = payload["execution"]["nodes"][1]
    node.pop("top_k")
    node["retrieval"] = {"mode": "keyword", "top_k": 2}
    new = c.post(f"{base}/{old['pipeline_id']}/versions", json=payload).json()
    assert new["execution"] == payload["execution"]
    with patch.object(
        generation.OpenRouterChat,
        "generate",
        side_effect=AssertionError("No evidence must skip generation"),
    ):
        for route, body in [
            (
                f"{base}/{old['pipeline_id']}/versions/{new['id']}/runs",
                {"question": "absent"},
            ),
            (
                f"{base}/preview-runs",
                {"question": "absent", "execution": payload["execution"]},
            ),
        ]:
            response = c.post(route, json=body)
            assert response.status_code == 202, response.text
            run = c.get(f"/api/projects/{p}/query-runs/{response.json()['id']}").json()
            assert run["status"] == "insufficient_evidence", run
            assert run["snapshot"]["retrieval"] == node["retrieval"]
            assert run["snapshot"]["retrieval_result"]["items"] == []
    assert c.get(f"{base}/{old['pipeline_id']}/versions/{old['id']}").json() == old


def test_experiment_keeps_hybrid_settings(experiment_api, monkeypatch):  # noqa: F811
    c, engine, p, _, versions = experiment_api
    payload = deepcopy({k: versions[0][k] for k in ("name", "execution", "layout")})
    payload["execution"]["schema_version"] = 2
    node = payload["execution"]["nodes"][1]
    node.pop("top_k")
    node["retrieval"] = HybridSearch(
        mode="hybrid",
        top_k=2,
        vector_candidates=4,
        keyword_candidates=7,
        vector_weight=0,
    ).model_dump()
    version = c.post(
        f"/api/projects/{p}/pipelines/{versions[0]['pipeline_id']}/versions",
        json=payload,
    ).json()
    ds = imported(c, p, b"question,reference_answer\nabcd,abcd\n")
    submitted = c.post(
        f"/api/projects/{p}/experiments",
        json={
            "name": "Hybrid snapshot",
            "dataset_version_id": ds["id"],
            "pipeline_version_ids": [version["id"]],
            "metrics": ["faithfulness"],
        },
    )
    assert submitted.status_code == 202, submitted.text
    monkeypatch.setattr(
        embeddings,
        "provider_for",
        lambda _: pytest.fail("Zero vector weight must skip embeddings"),
    )
    monkeypatch.setattr(
        "app.evaluation.evaluator.provider_for", lambda _: JudgeDouble()
    )
    with patch.object(
        generation.OpenRouterChat,
        "generate",
        return_value=generation.Completion("abcd [S1]", "test/chat", None, None),
    ):
        result = drive(c, engine, p, submitted.json()["id"])
    assert result["status"] == "succeeded", result
    snapshot = result["items"][0]["output"]["snapshot"]
    assert snapshot["retrieval"] == node["retrieval"]
    assert snapshot["retrieval_result"]["diagnostics"]["vector_ms"] is None
    assert snapshot["evidence"][0]["lexical_score"] > 0


def test_populated_lexical_migration_preserves_evidence(index_api, database):  # noqa: F811
    c, engine, p, _, _ = index_api
    prepared(c, engine, p)
    index = create(c, p)
    process_index(UUID(index["id"]), engine)
    before = retrieve(c, p, index, {"mode": "keyword"}).json()["items"]
    _, env = database
    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0006"], env=env, check=True
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True
    )
    after = retrieve(c, p, index, {"mode": "keyword"}).json()["items"]
    assert before == after
    assert retrieve(c, p, index, {"mode": "vector"}).json()["items"][0][
        "cosine_distance"
    ] == pytest.approx(0)
