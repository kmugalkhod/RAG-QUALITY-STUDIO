from datetime import timedelta
from uuid import UUID
from unittest.mock import patch
import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session
from app.core.config import settings
from app.evaluation import evaluator
from app.models.experiment import Dataset, DatasetVersion, Experiment, ExperimentItem
from app.providers.generation import Completion, GenerationError
from app.services import datasets, experiments
from app.workers.experiments import run_step, dispatch_experiments_once, now
from test_pipelines import pipeline_api, draft  # noqa: F401
from test_queries import query_api  # noqa: F401
from test_indexes import index_api, embedding_config  # noqa: F401
from test_documents import documents_api  # noqa: F401


@pytest.mark.parametrize(
    "data,reason",
    [
        (b"bad\nx\n", "headers"),
        (b"question,question\na,b\n", "headers"),
        (b'question\n""\n', "Question"),
        (b"question\na,b\n", "Column"),
        (b'question\n"unclosed', "CSV"),
        (b"question\n\xff", "UTF-8"),
        (b"question\n", "at least"),
    ],
)
def test_csv_validation(data, reason):
    result = datasets.preview(data)
    assert reason in result["errors"][0]["message"]
    assert result["errors"][0]["row"] >= 1


def test_csv_bounds_and_quoted_unicode(monkeypatch):
    result = datasets.preview(
        'question,reference_answer\r\n"What, café?","Line one\nline two"\n'.encode()
    )
    assert (
        not result["errors"]
        and result["rows"][0]["reference_answer"] == "Line one\nline two"
    )
    monkeypatch.setattr(settings, "dataset_max_rows", 1)
    assert datasets.preview(b"question\na\nb\n")["errors"][0]["row"] == 3
    monkeypatch.setattr(settings, "dataset_max_bytes", 5)
    with pytest.raises(Exception) as exc:
        datasets.preview(b"question\na\n")
    assert exc.value.status_code == 413


def test_metric_requirements_and_export():
    output = {
        "status": "insufficient_evidence",
        "answer": "INSUFFICIENT_EVIDENCE",
        "snapshot": {"evidence": [{"text": "data"}]},
    }
    assert (
        evaluator.precondition("context_recall", {}, output)["reason"]
        == "missing_reference"
    )
    assert evaluator.precondition("faithfulness", {}, output)["reason"] == "abstention"
    assert (
        evaluator.precondition("context_recall", {"reference_answer": "truth"}, output)
        is None
    )
    for value in ["=SUM(1,2)", " +1", "\ttext", "@calc", "-2", "\rformula"]:
        assert experiments.safe_cell(value).startswith("'")
    assert experiments.safe_cell("ordinary") == "ordinary"


@pytest.fixture
def experiment_api(pipeline_api, monkeypatch):  # noqa: F811
    c, engine, p, q, index = pipeline_api
    monkeypatch.setattr(settings, "evaluator_model", "test/judge")
    v1 = c.post(f"/api/projects/{p}/pipelines", json=draft(index["id"])).json()
    payload = draft(index["id"])
    payload["execution"]["nodes"][1]["top_k"] = 2
    v2 = c.post(
        f"/api/projects/{p}/pipelines/{v1['pipeline_id']}/versions", json=payload
    ).json()
    yield c, engine, p, q, [v1, v2]
    with Session(engine) as session:
        for model in [ExperimentItem, Experiment, DatasetVersion, Dataset]:
            session.execute(
                delete(model).where(model.project_id.in_([UUID(p), UUID(q)]))
            )
        session.commit()


def imported(
    c,
    p,
    data=b"question,reference_answer\nfirst?,truth\nsecond?,\nthird?,truth\n",
    **kwargs,
):
    root = f"/api/projects/{p}/datasets"
    preview = c.post(root + "/preview", files={"file": ("data.csv", data)}).json()
    response = c.post(
        root,
        files={"file": ("data.csv", data)},
        data={"name": "Reviewed", "content_hash": preview["content_hash"], **kwargs},
    )
    assert response.status_code == 201, response.text
    return response.json()


def submitted(fixture):
    c, engine, p, q, versions = fixture
    dataset = imported(c, p)
    payload = {
        "name": "Comparison",
        "dataset_version_id": dataset["id"],
        "pipeline_version_ids": [v["id"] for v in versions],
        "metrics": list(evaluator.METRICS),
    }
    response = c.post(f"/api/projects/{p}/experiments", json=payload)
    assert response.status_code == 202, response.text
    return response.json(), dataset, payload


class JudgeDouble:
    def score(self, metric, row, output, guard=None):
        if guard:
            guard()
        blocked = evaluator.precondition(metric, row, output)
        if blocked:
            return blocked
        if metric == "faithfulness" and row["question"] == "third?":
            return evaluator.unavailable("Deterministic judge failure", "failed")
        return {
            "status": "succeeded",
            "value": 0.75,
            "reason": "test verdict",
            "evaluation_cost_usd": None,
        }


def drive(c, engine, p, id):
    for _ in range(50):
        run = c.get(f"/api/projects/{p}/experiments/{id}").json()
        if run["status"] not in ("queued", "running"):
            return run
        run_step(UUID(id), engine)
    pytest.fail("Experiment never completed")


def test_complete_snapshots_scope_denominators(experiment_api):
    c, engine, p, q, versions = experiment_api
    run, ds, payload = submitted(experiment_api)
    new_ds = imported(c, p, b"question\nchanged?\n", dataset_id=ds["dataset_id"])
    assert new_ds["version"] == 2
    root = f"/api/projects/{p}/experiments/{run['id']}"
    assert c.get(root.replace(p, q)).status_code == 404
    assert c.post(root.replace(p, q) + "/cancel").status_code == 404
    assert c.get(root.replace(p, q) + "/export.csv").status_code == 404
    assert c.get(f"/api/projects/{q}/datasets/{ds['id']}").status_code == 404
    assert c.post(f"/api/projects/{q}/experiments", json=payload).status_code == 404
    with (
        patch(
            "app.providers.generation.OpenRouterChat.generate",
            return_value=Completion(
                "Answer [S1]", "test/chat", {"total_tokens": 20}, None
            ),
        ) as gen,
        patch("app.evaluation.evaluator.provider_for", return_value=JudgeDouble()),
    ):
        done = drive(c, engine, p, run["id"])
        run_step(UUID(run["id"]), engine)
        assert gen.call_count == 6
    assert done["status"] == "succeeded" and done["progress"] == 6
    assert (
        done["snapshot"] == run["snapshot"]
        and len(done["snapshot"]["dataset"]["rows"]) == 3
    )
    assert done["summary"]["paired"]["faithfulness"]["count"] == 2
    assert done["summary"]["paired"]["context_recall"]["count"] == 2
    metric = done["summary"]["candidates"][0]["metrics"]["context_recall"]
    assert metric["scored"] == 2 and metric["missing_reference"] == 1
    assert done["summary"]["candidates"][0]["generation_cost_usd"]["known_sum"] is None
    for item in done["items"]:
        actual = c.get(f"/api/projects/{p}/query-runs/{item['query_run_id']}").json()
        assert item["output"]["snapshot"]["evidence"] == actual["snapshot"]["evidence"]
        assert actual["pipeline_version_id"] == versions[item["candidate"]]["id"]
    assert "reference_answer" in c.get(root + "/export.csv").text


def test_partial_generation_failure_and_queued_cancel(experiment_api):
    c, engine, p, _, _ = experiment_api
    run, _, _ = submitted(experiment_api)
    with (
        patch(
            "app.providers.generation.OpenRouterChat.generate",
            side_effect=[
                GenerationError("bounded failure"),
                *[Completion("Answer [S1]", "test/chat", None, None)] * 5,
            ],
        ),
        patch("app.evaluation.evaluator.provider_for", return_value=JudgeDouble()),
    ):
        done = drive(c, engine, p, run["id"])
    assert done["progress"] == 6 and done["items"][0]["status"] == "failed"
    assert done["items"][1]["status"] == "succeeded"
    assert done["summary"]["paired"]["response_relevancy"]["count"] == 2
    other, _, _ = submitted(experiment_api)
    cancelled = c.post(f"/api/projects/{p}/experiments/{other['id']}/cancel").json()
    assert cancelled["status"] == "cancelled"
    with patch("app.providers.generation.provider_for") as provider:
        run_step(UUID(other["id"]), engine)
        provider.assert_not_called()


def test_inflight_cancel_and_duplicate_delivery(experiment_api):
    c, engine, p, _, _ = experiment_api
    run, _, _ = submitted(experiment_api)

    def generate(*args):
        run_step(UUID(run["id"]), engine)  # Duplicate while original holds claim.
        response = c.post(f"/api/projects/{p}/experiments/{run['id']}/cancel").json()
        assert response["cancel_requested"] and response["status"] == "running"
        return Completion("Retained answer [S1]", "test/chat", None, None)

    with patch(
        "app.providers.generation.OpenRouterChat.generate", side_effect=generate
    ) as gen:
        run_step(UUID(run["id"]), engine)
        assert gen.call_count == 1
    done = c.get(f"/api/projects/{p}/experiments/{run['id']}").json()
    assert done["status"] == "cancelled"
    assert done["items"][0]["output"]["answer"] == "Retained answer [S1]"
    assert all(item["status"] == "skipped" for item in done["items"])


def test_stale_metric_recovery_preserves_answer(experiment_api):
    c, engine, p, _, _ = experiment_api
    run, _, _ = submitted(experiment_api)
    with patch(
        "app.providers.generation.OpenRouterChat.generate",
        return_value=Completion("Answer [S1]", "test/chat", None, None),
    ):
        run_step(UUID(run["id"]), engine)
    with Session(engine) as session:
        job = session.get(Experiment, UUID(run["id"]))
        job.status = "running"
        job.started_at = now() - timedelta(seconds=500)
        item = session.get(ExperimentItem, (job.id, 0, 0))
        item.stage = "faithfulness"
        session.commit()
    sent = []
    dispatch_experiments_once(engine, send=sent.append)
    assert sent == [UUID(run["id"])]
    with (
        patch(
            "app.providers.generation.OpenRouterChat.generate",
            return_value=Completion("Answer [S1]", "test/chat", None, None),
        ) as gen,
        patch("app.evaluation.evaluator.provider_for", return_value=JudgeDouble()),
    ):
        done = drive(c, engine, p, run["id"])
        assert gen.call_count == 5
    assert done["items"][0]["metrics"]["faithfulness"]["status"] == "failed"
    assert done["items"][0]["output"]["answer"] == "Answer [S1]"


def test_ragas_adapter_executes_real_metrics_with_structured_doubles(monkeypatch):
    from pydantic import SecretStr
    from app.providers import generation, embeddings

    monkeypatch.setattr(settings, "evaluator_model", "test/judge")
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr("test"))
    config = evaluator.configured(list(evaluator.METRICS))
    output = {
        "status": "succeeded",
        "answer": "Apples grow.",
        "snapshot": {"evidence": [{"text": "Apples grow in the orchard."}]},
    }
    row = {"question": "What grows?", "reference_answer": "Apples grow."}
    responses = [
        '{"statements":["Apples grow."]}',
        '{"statements":[{"statement":"Apples grow.","reason":"Supported.","verdict":1}]}',
        *['{"question":"What grows?","noncommittal":0}'] * 3,
        '{"classifications":[{"statement":"Apples grow.","reason":"Supported.","attributed":1}]}',
    ]

    class Vectors:
        def embed(self, texts):
            return [[1.0, 0.0] for _ in texts]

    with (
        patch.object(
            generation.OpenRouterChat,
            "generate",
            side_effect=[
                Completion(text, "test/judge", {"total_tokens": 10}, 0.001)
                for text in responses
            ],
        ) as judge,
        patch.object(embeddings, "provider_for", return_value=Vectors()),
    ):
        result = [
            evaluator.RagasEvaluator(config).score(metric, row, output)
            for metric in evaluator.METRICS
        ]
    assert [r["value"] for r in result] == [1.0, 1.0, 1.0], result
    assert judge.call_count == 6
    assert result[0]["evaluation_cost_usd"] == 0.002
    assert result[1]["evaluation_llm_cost_usd"] == 0.003
    assert result[1]["evaluation_cost_usd"] is None
    assert (
        result[0]["calls"][1]["structured_output"]["statements"][0]["reason"]
        == "Supported."
    )


def test_ragas_invalid_and_undefined_output(monkeypatch):
    from pydantic import SecretStr
    from app.providers import generation

    monkeypatch.setattr(settings, "evaluator_model", "test/judge")
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr("test"))
    config = evaluator.configured(["faithfulness"])
    output = {
        "status": "succeeded",
        "answer": "Hello",
        "snapshot": {"evidence": [{"text": "Evidence"}]},
    }
    with patch.object(
        generation.OpenRouterChat,
        "generate",
        return_value=Completion('{"statements":[]}', "test/judge", None, None),
    ) as judge:
        result = evaluator.RagasEvaluator(config).score(
            "faithfulness", {"question": "Q"}, output
        )
    assert (
        result["status"] == "unavailable"
        and result["value"] is None
        and judge.call_count == 1
    )
    with patch.object(
        generation.OpenRouterChat, "generate", side_effect=RuntimeError("secret-key")
    ):
        result = evaluator.RagasEvaluator(config).score(
            "faithfulness", {"question": "Q"}, output
        )
    assert result["status"] == "failed" and "secret-key" not in str(result)


def test_cancel_during_retrieval_prevents_generation(experiment_api):
    from app.services import indexes

    c, engine, p, _, _ = experiment_api
    run, _, _ = submitted(experiment_api)
    original = indexes.retrieve

    def retrieve(*args):
        result = original(*args)
        c.post(f"/api/projects/{p}/experiments/{run['id']}/cancel").raise_for_status()
        return result

    with (
        patch.object(indexes, "retrieve", side_effect=retrieve),
        patch("app.providers.generation.OpenRouterChat.generate") as generation,
    ):
        run_step(UUID(run["id"]), engine)
        generation.assert_not_called()
    assert (
        c.get(f"/api/projects/{p}/experiments/{run['id']}").json()["status"]
        == "cancelled"
    )
