"""Real PostgreSQL concurrency and admission capacity checks.

This file runs last because it commits synthetic rows to the isolated _test database.
"""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from statistics import median
from threading import Barrier
from time import monotonic, sleep
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.deployment import (
    AnswerDeployment,
    AnswerDeploymentKey,
    AnswerDeploymentRelease,
    DeployedAnswerRun,
    DeploymentUsageEntry,
)
from app.models.index import IndexVersion, KnowledgeSet
from app.models.pipeline import Pipeline, PipelineVersion
from app.models.project import Project
from app.schemas.pipeline import DEFAULT_TEMPLATE
from app.services import deployed_runs
from app.services.deployments import _hash


def _seed(engine, embedding_config=None):
    actor = uuid4()
    with Session(engine) as session:
        project = Project(
            name="Concurrency fixture", organization_id="org_concurrent_test"
        )
        session.add(project)
        session.flush()
        pipeline = Pipeline(
            project_id=project.id, name="Concurrent answer", kind="answer"
        )
        knowledge = KnowledgeSet(project_id=project.id, name="Concurrent index")
        session.add_all([pipeline, knowledge])
        session.flush()
        index = IndexVersion(
            project_id=project.id,
            knowledge_set_id=knowledge.id,
            version=1,
            dimensions=3,
            embedding_config=embedding_config or {"provider": "test"},
            status="succeeded",
            chunk_count=1,
            embedded_count=1,
            attempts=0,
            failures=0,
        )
        session.add(index)
        session.flush()
        kinds = ("question", "retriever", "prompt", "llm", "answer")
        execution = {
            "schema_version": 1,
            "nodes": [
                {"id": "question", "type": "question"},
                {
                    "id": "retriever",
                    "type": "retriever",
                    "index_id": str(index.id),
                    "top_k": 1,
                },
                {"id": "prompt", "type": "prompt", "template": DEFAULT_TEMPLATE},
                {
                    "id": "llm",
                    "type": "llm",
                    "model": "test/chat",
                    "max_tokens": 512,
                    "temperature": 0,
                },
                {"id": "answer", "type": "answer"},
            ],
            "edges": [{"source": a, "target": b} for a, b in zip(kinds, kinds[1:])],
        }
        version = PipelineVersion(
            project_id=project.id,
            pipeline_id=pipeline.id,
            version=1,
            name="Concurrent answer",
            execution=execution,
            layout={},
        )
        session.add(version)
        session.flush()
        deployment = AnswerDeployment(
            organization_id=project.organization_id,
            project_id=project.id,
            pipeline_id=pipeline.id,
            name="Concurrent",
            created_by=actor,
            rate_per_minute=30,
            concurrent_runs=2,
            queued_runs=20,
            daily_budget_usd=Decimal("5"),
            monthly_budget_usd=Decimal("20"),
        )
        session.add(deployment)
        session.flush()
        release = AnswerDeploymentRelease(
            deployment_id=deployment.id,
            organization_id=project.organization_id,
            project_id=project.id,
            pipeline_id=pipeline.id,
            pipeline_version_id=version.id,
            index_id=index.id,
            release_number=1,
            execution=execution,
            execution_sha256=_hash(execution),
            embedding_config=index.embedding_config,
            embedding_sha256=_hash(index.embedding_config),
            schema_version=1,
            created_by=actor,
            note="",
        )
        session.add(release)
        session.flush()
        deployment.active_release_id = release.id
        deployment.state = "active"
        key = AnswerDeploymentKey(
            deployment_id=deployment.id,
            organization_id=project.organization_id,
            project_id=project.id,
            client_id=uuid4(),
            prefix="rqs_live_" + uuid4().hex[:16],
            secret_hash="0" * 64,
            pepper_version="test",
            label="Load",
            created_by=actor,
        )
        session.add(key)
        session.commit()
        return deployment.id, key.id


def test_concurrent_duplicate_and_queue_budget_atomicity(database, monkeypatch):
    engine, _ = database
    deployment_id, key_id = _seed(engine)
    monkeypatch.setattr(deployed_runs, "_validated_release", lambda *args: None)
    monkeypatch.setattr(
        deployed_runs.deployment_pricing, "worst_case", lambda *args: Decimal("0.01")
    )
    monkeypatch.setattr(settings, "deployment_key_rpm", 100)
    monkeypatch.setattr(settings, "deployment_rpm", 100)
    monkeypatch.setattr(settings, "deployment_org_rpm", 100)
    monkeypatch.setattr(settings, "deployment_queue_cap", 5)
    monkeypatch.setattr(settings, "deployment_org_queue_cap", 5)
    monkeypatch.setattr(settings, "deployment_global_queue_cap", 5)
    barrier = Barrier(8)

    def request(key):
        with Session(
            engine.execution_options(isolation_level="READ COMMITTED")
        ) as session:
            deployment = session.get(AnswerDeployment, deployment_id)
            credential = session.get(AnswerDeploymentKey, key_id)
            barrier.wait(timeout=10)
            start = monotonic()
            try:
                run, replay = deployed_runs.admit(
                    session, deployment, credential, "Same question?", key
                )
                return str(run.id), replay, monotonic() - start
            except HTTPException as error:
                session.rollback()
                return error.status_code, str(error.detail), monotonic() - start

    with ThreadPoolExecutor(max_workers=8) as pool:
        duplicate = list(pool.map(request, ["same"] * 8))
    assert len({result[0] for result in duplicate}) == 1
    assert sum(not result[1] for result in duplicate) == 1
    assert max(result[2] for result in duplicate) < 10

    barrier = Barrier(8)
    with ThreadPoolExecutor(max_workers=8) as pool:
        distinct = list(pool.map(request, [f"distinct-{n}" for n in range(8)]))
    assert sum(isinstance(result[0], str) for result in distinct) == 4
    assert (
        sum(result[0] == 429 and result[1] == "queue_full" for result in distinct) == 4
    )
    timings = sorted(result[2] for result in duplicate + distinct)
    print(
        "Admission latency seconds: "
        f"p50={median(timings):.4f} "
        f"p95={timings[int(len(timings) * 0.95) - 1]:.4f} "
        f"p99={timings[-1]:.4f}"
    )
    assert median(timings) < 5 and timings[int(len(timings) * 0.95) - 1] < 10
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(DeployedAnswerRun)
                .where(
                    DeployedAnswerRun.deployment_id == deployment_id,
                )
            )
            == 5
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(DeploymentUsageEntry)
                .where(
                    DeploymentUsageEntry.entry_type == "reservation",
                )
            )
            == 5
        )


def test_redis_celery_executes_a_pinned_answer_with_provider_doubles(
    database, monkeypatch
):
    from unittest.mock import patch

    from celery.contrib.testing.worker import start_worker
    from pydantic import SecretStr

    from app.providers import embeddings, generation
    from app.services import indexes
    from app.workers import deployed_answers

    engine, _ = database
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr("test-only"))
    monkeypatch.setattr(settings, "chat_model", "test/chat")
    monkeypatch.setattr(settings, "embedding_dimensions", 3)
    config = embeddings.configured().model_dump()
    deployment_id, key_id = _seed(engine, config)
    monkeypatch.setattr(deployed_runs, "_validated_release", lambda *args: None)
    monkeypatch.setattr(
        deployed_runs.deployment_pricing, "worst_case", lambda *args: Decimal("0.01")
    )
    run_ids = []
    with Session(engine.execution_options(isolation_level="READ COMMITTED")) as session:
        deployment = session.get(AnswerDeployment, deployment_id)
        credential = session.get(AnswerDeploymentKey, key_id)
        for number in range(8):
            run, replay = deployed_runs.admit(
                session,
                deployment,
                credential,
                "What is the return period?",
                f"broker-test-{number}",
            )
            assert not replay
            run_ids.append(run.id)

    original = deployed_answers.process_deployed
    monkeypatch.setattr(
        deployed_answers,
        "process_deployed",
        lambda value: original(value, engine),
    )
    evidence = {
        "document_id": str(uuid4()),
        "filename": "Returns policy",
        "page_number": 2,
        "rank": 1,
        "text": "Returns are accepted for 30 days.",
    }
    queue = f"deployed_answers_qa_{uuid4().hex[:12]}"
    with (
        patch.object(indexes, "retrieve", return_value={"items": [evidence]}),
        patch.object(
            generation.OpenRouterChat,
            "generate",
            return_value=generation.Completion(
                "Returns are accepted for 30 days. [S1]",
                "test/chat",
                {"total_tokens": 20},
                None,
            ),
        ) as provider,
        start_worker(
            deployed_answers.celery,
            pool="solo",
            concurrency=1,
            queues=[queue],
            perform_ping_check=False,
            shutdown_timeout=5,
        ),
    ):
        for run_id in run_ids:
            deployed_answers.execute_deployed.apply_async(
                args=[str(run_id)], queue=queue
            )
        deadline = monotonic() + 20
        while monotonic() < deadline:
            with Session(engine) as session:
                states = [session.get(DeployedAnswerRun, value) for value in run_ids]
                if all(
                    state.status in {"succeeded", "insufficient_evidence", "failed"}
                    for state in states
                ):
                    break
            sleep(0.1)
        else:
            raise AssertionError("Celery did not complete the accepted run")
    with Session(engine) as session:
        states = [session.get(DeployedAnswerRun, value) for value in run_ids]
        for state in states:
            assert state.status == "succeeded"
            assert state.answer == "Returns are accepted for 30 days. [S1]"
            assert state.citations[0]["excerpt"] == evidence["text"]
        for metric in ("queue", "execution"):
            values = sorted(state.timing_ms[metric] for state in states)
            print(
                f"Celery {metric} latency ms: p50={median(values):.1f} "
                f"p95={values[int(len(values) * 0.95) - 1]:.1f} "
                f"p99={values[-1]:.1f}"
            )
            assert values[-1] < 10000
    assert provider.call_count == len(run_ids)
