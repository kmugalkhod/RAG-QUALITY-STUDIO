from copy import deepcopy
from uuid import UUID, uuid4
from unittest.mock import patch
import pytest
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.document import Document
from app.models.pipeline import Pipeline, PipelineVersion
from app.models.query import QueryRun
from app.schemas.pipeline import Execution, PipelineSave, DEFAULT_TEMPLATE
from app.providers import generation
from app.services import pipelines
from test_queries import query_api  # noqa: F401
from test_indexes import index_api, embedding_config  # noqa: F401
from test_documents import documents_api  # noqa: F401
from test_ingestion_contracts import ingestion_draft


def draft(index_id):
    kinds = ["question", "retriever", "prompt", "llm", "answer"]
    nodes = [dict(id=k, type=k) for k in kinds]
    nodes[1].update(index_id=index_id, top_k=1)
    nodes[2]["template"] = DEFAULT_TEMPLATE
    nodes[3].update(model="test/chat", max_tokens=512, temperature=0)
    return dict(
        name="Evidence pipeline",
        execution=dict(
            schema_version=1,
            nodes=nodes,
            edges=[dict(source=a, target=b) for a, b in zip(kinds, kinds[1:])],
        ),
        layout=dict(positions={k: dict(x=i * 210, y=80) for i, k in enumerate(kinds)}),
    )


@pytest.fixture
def pipeline_api(query_api, monkeypatch):  # noqa: F811
    c, engine, p, q, index = query_api
    monkeypatch.setattr(settings, "chat_models", ["test/other"])
    monkeypatch.setattr("app.db.session.engine", engine)
    yield c, engine, p, q, index
    with Session(engine) as session:
        session.execute(
            delete(QueryRun).where(QueryRun.project_id.in_([UUID(p), UUID(q)]))
        )
        session.execute(
            delete(PipelineVersion).where(
                PipelineVersion.project_id.in_([UUID(p), UUID(q)])
            )
        )
        session.execute(
            delete(Pipeline).where(Pipeline.project_id.in_([UUID(p), UUID(q)]))
        )
        session.commit()


def test_save_reopen_versions_execution_and_duplicate(pipeline_api):
    c, _, p, q, index = pipeline_api
    base = f"/api/projects/{p}/pipelines"
    payload = draft(index["id"])
    response = c.post(base, json=payload)
    assert response.status_code == 201, response.text
    first = response.json()
    path = f"{base}/{first['pipeline_id']}/versions"
    assert c.get(path + "/" + first["id"]).json() == first
    assert (
        first["execution"] == payload["execution"]
        and first["layout"] == payload["layout"]
    )
    assert c.get(base).json()["items"][0]["name"] == payload["name"]
    with patch.object(
        generation.OpenRouterChat,
        "generate",
        return_value=generation.Completion(
            "Answer [S1]", "test/chat", {"total_tokens": 20}, None
        ),
    ) as provider:
        accepted = c.post(
            path + "/" + first["id"] + "/runs", json={"question": "abcd?"}
        )
        assert accepted.status_code == 202, accepted.text
        assert accepted.json()["status"] == "running"
        run1 = c.get(f"/api/projects/{p}/query-runs/{accepted.json()['id']}").json()
        assert run1["status"] == "succeeded", run1
        assert len(run1["snapshot"]["evidence"]) == 1
        assert run1["snapshot"]["execution_engine"]["node_order"] == [
            node["id"] for node in payload["execution"]["nodes"]
        ]
        assert run1["snapshot"]["execution_engine"]["composition"] == (
            "LCEL RunnableSequence"
        )
        assert provider.call_args.args[1]["model"] == "test/chat"
        assert run1["pipeline_version_id"] == first["id"]
        payload["execution"]["nodes"][1]["top_k"] = 3
        payload["execution"]["nodes"][2]["template"] = (
            "Use three bullet points. {question} {context}"
        )
        payload["execution"]["nodes"][3].update(
            model="test/other", temperature=0.7, max_tokens=768
        )
        payload["layout"]["positions"]["llm"] = dict(x=123, y=-42)
        second = c.post(path, json=payload).json()
        assert second["version"] == 2
        accepted2 = c.post(
            path + "/" + second["id"] + "/runs", json={"question": "abcd?"}
        )
        run2 = c.get(f"/api/projects/{p}/query-runs/{accepted2.json()['id']}").json()
        assert run2["status"] == "succeeded", run2
        assert len(run2["snapshot"]["evidence"]) == 3
        assert run2["snapshot"]["top_k"] == 3
        assert run2["snapshot"]["generation_config"]["model"] == "test/other"
        assert provider.call_args.args[1]["temperature"] == 0.7
        assert provider.call_args.args[1]["max_tokens"] == 768
        assert "Use three bullet points." in provider.call_args.args[0][-1]["content"]
        assert run2["snapshot"]["messages"] != run1["snapshot"]["messages"]
    assert c.get(path + "/" + first["id"]).json() == first
    assert c.get(f"/api/projects/{p}/query-runs/{run1['id']}").json() == run1
    assert c.get(path).json()["total"] == 2
    copy = c.post(base, json=payload).json()
    assert copy["pipeline_id"] != first["pipeline_id"] and copy["version"] == 1
    assert (
        copy["execution"] == second["execution"] and copy["layout"] == second["layout"]
    )
    assert c.get(path.replace(p, q)).status_code == 404
    assert c.get((path + "/" + first["id"]).replace(p, q)).status_code == 404
    assert c.post(path.replace(p, q), json=payload).status_code == 404
    assert (
        c.post(
            (path + "/" + first["id"] + "/runs").replace(p, q), json={"question": "a"}
        ).status_code
        == 404
    )
    assert c.post(f"/api/projects/{q}/pipelines", json=payload).status_code == 404
    assert c.get(f"/api/projects/{q}/pipelines").json()["total"] == 0


@pytest.mark.parametrize(
    "case",
    [
        "cycle",
        "branch",
        "disconnect",
        "unknown",
        "duplicate",
        "missing",
        "settings",
        "template",
        "expression",
        "layout",
        "model",
        "version",
        "extra",
    ],
)
def test_direct_api_invalid_graphs(pipeline_api, case):
    c, _, p, _, index = pipeline_api
    payload = draft(index["id"])
    ex = payload["execution"]
    if case == "cycle":
        ex["edges"][-1] = dict(source="llm", target="question")
    if case == "branch":
        ex["edges"].append(dict(source="question", target="llm"))
    if case == "disconnect":
        ex["edges"].pop()
    if case == "unknown":
        ex["nodes"][0]["type"] = "code"
    if case == "duplicate":
        ex["nodes"][0]["id"] = "retriever"
    if case == "missing":
        ex["nodes"].pop()
    if case == "settings":
        ex["nodes"][1]["top_k"] = 51
    if case == "template":
        ex["nodes"][2]["template"] = "{question}"
    if case == "expression":
        ex["nodes"][2]["template"] = "{question} {context} {question.__class__}"
    if case == "layout":
        payload["layout"]["positions"]["other"] = dict(x=0, y=0)
    if case == "model":
        ex["nodes"][3]["model"] = "not/configured"
    if case == "version":
        ex["schema_version"] = 2
    if case == "extra":
        ex["nodes"][0]["code"] = "print(1)"
    response = c.post(f"/api/projects/{p}/pipelines", json=payload)
    assert response.status_code == 422, response.text
    assert c.get(f"/api/projects/{p}/pipelines").json()["total"] == 0


def test_unready_removed_model_failed_run_and_recovery(pipeline_api, monkeypatch):
    from test_indexes import create
    from sqlalchemy import update
    from datetime import datetime, timedelta, timezone

    c, engine, p, _, index = pipeline_api
    base = f"/api/projects/{p}/pipelines"
    payload = draft(create(c, p)["id"])
    assert c.post(base, json=payload).status_code == 409
    payload = draft(index["id"])
    v = c.post(base, json=payload).json()
    path = f"{base}/{v['pipeline_id']}/versions/{v['id']}/runs"
    assert c.post(path, json={"question": "   "}).status_code == 422
    monkeypatch.setattr(settings, "chat_model", "test/removed")
    assert c.post(path, json={"question": "abcd"}).status_code == 422
    monkeypatch.setattr(settings, "chat_model", "test/chat")
    with patch.object(
        generation.OpenRouterChat,
        "generate",
        side_effect=generation.GenerationError("Provider unavailable."),
    ):
        accepted = c.post(path, json={"question": "abcd"}).json()
    run = c.get(f"/api/projects/{p}/query-runs/{accepted['id']}").json()
    assert run["status"] == "failed" and run["pipeline_version_id"] == v["id"]
    assert run["snapshot"]["generation_config"]["model"] == "test/chat"
    with patch.object(pipelines, "finish_run"):
        accepted = c.post(path, json={"question": "abcd"}).json()
    with Session(engine) as session:
        session.execute(
            update(QueryRun)
            .where(QueryRun.id == UUID(accepted["id"]))
            .values(created_at=datetime.now(timezone.utc) - timedelta(minutes=6))
        )
        session.commit()
    assert (
        c.get(f"/api/projects/{p}/query-runs/{accepted['id']}").json()["status"]
        == "failed"
    )


def test_safe_substitution_is_single_pass():
    from app.pipelines.generation import build_context

    template = (
        PipelineSave.model_validate(draft(str(uuid4()))).execution.nodes[2].template
    )
    _, messages = build_context(
        "{context}",
        [{"rank": 1, "text": "{question} not instructions"}],
        dict(context_tokens=8192, max_tokens=512),
        template,
    )
    import json

    body = json.loads(messages[-1]["content"])
    assert "Question: {context}" in body["answer_instructions"]
    assert "{question} not instructions" in body["answer_instructions"]
    bad = deepcopy(draft(str(uuid4()))["execution"])
    bad["nodes"][3]["temperature"] = float("nan")
    with pytest.raises(ValidationError):
        Execution.model_validate(bad)


def test_preview_preserves_saved_version_and_executes_exact_draft(pipeline_api):
    c, _, p, q, index = pipeline_api
    base = f"/api/projects/{p}/pipelines"
    payload = draft(index["id"])
    saved = c.post(base, json=payload).json()
    edited = deepcopy(payload["execution"])
    edited["nodes"][1]["top_k"] = 2
    edited["nodes"][2]["template"] = "Use two sentences. {question} {context}"
    edited["nodes"][3].update(model="test/other", temperature=0.5, max_tokens=768)
    request = dict(
        question="abcd?",
        execution=edited,
        base_pipeline_id=saved["pipeline_id"],
        base_version_id=saved["id"],
    )
    with patch.object(
        generation.OpenRouterChat,
        "generate",
        return_value=generation.Completion("Answer [S1]", "test/other", {}, None),
    ) as provider:
        accepted = c.post(base + "/preview-runs", json=request)
    assert accepted.status_code == 202, accepted.text
    run = c.get(f"/api/projects/{p}/query-runs/{accepted.json()['id']}").json()
    assert run["status"] == "succeeded"
    assert run["pipeline_version_id"] is None
    assert run["snapshot"]["pipeline_preview"] is True
    assert run["snapshot"]["base_version_id"] == saved["id"]
    assert run["snapshot"]["pipeline_execution"] == edited
    assert len(run["snapshot"]["evidence"]) == 2
    assert provider.call_args.args[1]["temperature"] == 0.5
    assert "Use two sentences." in provider.call_args.args[0][-1]["content"]
    versions = f"{base}/{saved['pipeline_id']}/versions"
    assert c.get(versions).json()["total"] == 1
    assert c.get(versions + "/" + saved["id"]).json() == saved
    assert c.post(base.replace(p, q) + "/preview-runs", json=request).status_code == 404
    request["execution"]["nodes"][1]["top_k"] = 51
    assert c.post(base + "/preview-runs", json=request).status_code == 422
    request["execution"]["nodes"][1]["top_k"] = 2
    request.pop("base_version_id")
    assert c.post(base + "/preview-runs", json=request).status_code == 422


def test_pipeline_kind_filtering_and_ingestion_version_persistence(pipeline_api):
    c, engine, p, q, index = pipeline_api
    base = f"/api/projects/{p}/pipelines"
    answer = c.post(base, json=draft(index["id"]))
    assert answer.status_code == 201, answer.text
    ingestion_payload = ingestion_draft()
    embed = next(
        node
        for node in ingestion_payload["execution"]["nodes"]
        if node["type"] == "embed"
    )
    embed.update(
        provider=settings.embedding_provider,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        config_version=settings.embedding_revision,
    )
    ingestion = c.post(base, json=ingestion_payload)
    assert ingestion.status_code == 201, ingestion.text
    saved = ingestion.json()

    answer_page = c.get(base + "?kind=answer").json()
    ingestion_page = c.get(base + "?kind=ingestion").json()
    assert answer_page["total"] == 1
    assert answer_page["items"][0]["kind"] == "answer"
    assert ingestion_page["total"] == 1
    assert ingestion_page["items"][0]["kind"] == "ingestion"
    assert c.get(base).json()["total"] == 2
    assert c.get(base + "?kind=other").status_code == 422

    versions = f"{base}/{saved['pipeline_id']}/versions"
    assert c.get(versions + "/" + saved["id"]).json() == saved
    assert c.post(versions, json=draft(index["id"])).status_code == 409
    assert (
        c.post(
            versions + "/" + saved["id"] + "/runs", json={"question": "No"}
        ).status_code
        == 409
    )
    assert c.get(versions.replace(p, q)).status_code == 404
    with Session(engine) as session:
        document_id = session.scalar(
            select(Document.id).where(Document.project_id == UUID(p))
        )
    cross_project = deepcopy(ingestion_payload)
    cross_project["execution"]["nodes"][0]["config"] = {
        "kind": "existing_files",
        "document_ids": [str(document_id)],
    }
    assert c.post(base.replace(p, q), json=cross_project).status_code == 404


def test_invalid_ingestion_graph_never_persists(pipeline_api):
    c, _, p, _, _ = pipeline_api
    base = f"/api/projects/{p}/pipelines"
    payload = ingestion_draft()
    payload["execution"]["edges"][-1] = {
        "source": "publish",
        "target": "extract",
    }
    response = c.post(base, json=payload)
    assert response.status_code == 422, response.text
    assert c.get(base + "?kind=ingestion").json()["total"] == 0


def rerank_draft(index_id, model="test/other", top_k=3, top_n=2):
    """A schema v3 save: Question → Retriever → Rerank → Prompt → LLM → Answer."""

    payload = draft(index_id)
    execution = payload["execution"]
    execution["schema_version"] = 3
    retriever = execution["nodes"][1]
    del retriever["top_k"]
    retriever["retrieval"] = {"mode": "vector", "top_k": top_k}
    execution["nodes"].insert(
        2, dict(id="rerank", type="rerank", model=model, top_n=top_n)
    )
    ids = [node["id"] for node in execution["nodes"]]
    execution["edges"] = [dict(source=a, target=b) for a, b in zip(ids, ids[1:])]
    payload["layout"]["positions"] = {
        k: dict(x=0, y=i * 116) for i, k in enumerate(ids)
    }
    return payload


def rerank_double(order="3, 1", error=None):
    """Answers rerank calls (they disable reasoning) and answer calls apart."""

    def generate(messages, config):
        if "reasoning" in config:
            if error:
                raise error
            return generation.Completion(
                order, "test/other", {"total_tokens": 9}, 0.0001
            )
        return generation.Completion(
            "Answer [S1]", "test/chat", {"total_tokens": 20}, 0.002
        )

    return generate


def test_rerank_node_saves_runs_falls_back_and_can_be_removed(pipeline_api):
    c, _, p, q, index = pipeline_api
    base = f"/api/projects/{p}/pipelines"
    payload = rerank_draft(index["id"])
    response = c.post(base, json=payload)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved["execution"]["schema_version"] == 3
    assert saved["execution"]["nodes"][2] == {
        "id": "rerank",
        "type": "rerank",
        "model": "test/other",
        "top_n": 2,
    }
    versions = f"{base}/{saved['pipeline_id']}/versions"
    assert c.get(f"{versions}/{saved['id']}").json() == saved
    runs = f"{versions}/{saved['id']}/runs"
    with patch.object(
        generation.OpenRouterChat, "generate", side_effect=rerank_double("3, 1")
    ) as provider:
        accepted = c.post(runs, json={"question": "abcd?"})
        assert accepted.status_code == 202, accepted.text
        run = c.get(f"/api/projects/{p}/query-runs/{accepted.json()['id']}").json()
    assert run["status"] == "succeeded", run
    snapshot = run["snapshot"]
    assert snapshot["execution_engine"]["node_order"] == [
        "question",
        "retriever",
        "rerank",
        "prompt",
        "llm",
        "answer",
    ]
    assert snapshot["pipeline_execution"] == saved["execution"]
    record = snapshot["rerank"]
    assert record["status"] == "reranked" and record["model"] == "test/other"
    assert record["prompt_version"] == "rerank-v1"
    assert record["candidate_count"] == 3 and record["top_n"] == 2
    assert record["cost_usd"] == 0.0001 and snapshot["cost_usd"] == 0.002
    assert record["rerank_ms"] is not None and snapshot["rerank_ms"] is not None
    assert [(e["rank"], e["retriever_rank"]) for e in snapshot["evidence"]] == [
        (1, 3),
        (2, 1),
    ]
    assert [e["label"] for e in snapshot["evidence"]] == ["S1", "S2"]
    retrieved = {
        item["rank"]: item["text"] for item in snapshot["retrieval_result"]["items"]
    }
    assert snapshot["evidence"][0]["text"] == retrieved[3]
    rerank_call, answer_call = provider.call_args_list
    assert rerank_call.args[1]["model"] == "test/other"
    assert answer_call.args[1]["model"] == "test/chat"
    assert retrieved[3] in answer_call.args[0][-1]["content"]

    with patch.object(
        generation.OpenRouterChat,
        "generate",
        side_effect=rerank_double(error=generation.GenerationError("Provider down.")),
    ):
        accepted = c.post(runs, json={"question": "abcd?"})
        fallback = c.get(f"/api/projects/{p}/query-runs/{accepted.json()['id']}").json()
    assert fallback["status"] == "succeeded", fallback
    assert fallback["snapshot"]["rerank"]["status"] == "fallback"
    assert (
        fallback["snapshot"]["rerank"]["message"]
        == "Reranking failed; retriever order used"
    )
    assert [e["retriever_rank"] for e in fallback["snapshot"]["evidence"]] == [1, 2]

    # Removing the step saves an ordinary five-node version; v1 stays as saved.
    removed = c.post(versions, json=draft(index["id"]))
    assert removed.status_code == 201, removed.text
    assert removed.json()["version"] == 2
    assert len(removed.json()["execution"]["nodes"]) == 5
    assert c.get(f"{versions}/{saved['id']}").json() == saved
    assert c.post(versions.replace(p, q), json=payload).status_code == 404


@pytest.mark.parametrize("case", ["unapproved", "top_k", "v2", "layout"])
def test_invalid_rerank_saves_never_persist(pipeline_api, case):
    c, _, p, _, index = pipeline_api
    payload = rerank_draft(index["id"])
    if case == "unapproved":
        payload["execution"]["nodes"][2]["model"] = "not/approved"
    if case == "top_k":
        payload = rerank_draft(index["id"], top_k=2, top_n=3)
    if case == "v2":
        payload["execution"]["schema_version"] = 2
    if case == "layout":
        del payload["layout"]["positions"]["rerank"]
    response = c.post(f"/api/projects/{p}/pipelines", json=payload)
    assert response.status_code == 422, response.text
    if case == "unapproved":
        assert response.json()["detail"].startswith("Rerank:")
    assert c.get(f"/api/projects/{p}/pipelines").json()["total"] == 0


def test_preview_runs_an_unsaved_rerank_step(pipeline_api):
    c, _, p, _, index = pipeline_api
    base = f"/api/projects/{p}/pipelines"
    saved = c.post(base, json=draft(index["id"])).json()
    request = dict(
        question="abcd?",
        execution=rerank_draft(index["id"])["execution"],
        base_pipeline_id=saved["pipeline_id"],
        base_version_id=saved["id"],
    )
    with patch.object(
        generation.OpenRouterChat, "generate", side_effect=rerank_double("2")
    ):
        accepted = c.post(base + "/preview-runs", json=request)
    assert accepted.status_code == 202, accepted.text
    run = c.get(f"/api/projects/{p}/query-runs/{accepted.json()['id']}").json()
    assert run["status"] == "succeeded"
    assert [e["retriever_rank"] for e in run["snapshot"]["evidence"]] == [2, 1]
    assert c.get(f"{base}/{saved['pipeline_id']}/versions").json()["total"] == 1
