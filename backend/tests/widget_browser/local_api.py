"""Disposable localhost browser harness using real admission/worker and deterministic provider doubles."""

import json
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import engine
from app.models.deployment import DeployedAnswerRun
from app.models.index import IndexVersion, KnowledgeSet
from app.models.pipeline import Pipeline, PipelineVersion
from app.models.project import Project
from app.models.security import UserIdentity
from app.providers import embeddings
from app.schemas.deployment import DeploymentCreate
from app.schemas.pipeline import DEFAULT_TEMPLATE
from app.services import deployments
from app.core import deployment_auth
from app.workers import deployed_answers

FILE = Path(os.environ["WIDGET_LOCAL_CONFIG_FILE"])


def seed():
    with Session(engine) as session:
        if session.scalar(select(Project.id).limit(1)):
            if FILE.exists():
                return
            raise RuntimeError(
                "Browser test database is populated but the local key file is absent."
            )
        project = Project(
            name="Widget browser fixture", organization_id="org_widget_test"
        )
        actor = UserIdentity(external_subject="widget-browser-fixture")
        session.add_all([project, actor])
        session.flush()
        pipeline = Pipeline(project_id=project.id, name="Fixture answer", kind="answer")
        knowledge = KnowledgeSet(project_id=project.id, name="Fixture knowledge")
        session.add_all([pipeline, knowledge])
        session.flush()
        config = embeddings.configured().model_dump()
        index = IndexVersion(
            project_id=project.id,
            knowledge_set_id=knowledge.id,
            version=1,
            dimensions=settings.embedding_dimensions,
            embedding_config=config,
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
                    "model": settings.chat_model,
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
            name="Fixture answer",
            execution=execution,
            layout={"positions": {}},
        )
        session.add(version)
        session.commit()
        deployment, release = deployments.create(
            session,
            project,
            DeploymentCreate(
                name="Fixture assistant",
                pipeline_id=pipeline.id,
                pipeline_version_id=version.id,
                index_id=index.id,
                note="Local browser fixture",
            ),
            actor.id,
        )
        deployments.transition(
            session,
            deployment,
            "promote",
            actor.id,
            1,
            release_id=release.id,
            reason="Local fixture",
        )
        deployment.widget_enabled = True
        deployment.widget_origins = ["http://127.0.0.1:5275"]
        deployment.widget_branding = {
            "title": "Fixture assistant",
            "greeting": "Ask about the fixture",
            "color": "blue",
            "position": "right",
        }
        deployment.revision += 1
        session.commit()
        key, secret = deployment_auth.create_key(
            session, deployment, "Local customer site", None, actor.id
        )
        FILE.parent.mkdir(parents=True, exist_ok=True)
        FILE.write_text(
            json.dumps(
                {
                    "deployment_id": str(deployment.id),
                    "deployment_key": secret,
                    "site_origin": "http://127.0.0.1:5275",
                }
            )
        )
        FILE.chmod(0o600)


def fake_chain(**kwargs):
    updates = {
        "citations": {"valid": ["S1"]},
        "usage": {"prompt_tokens": 10, "completion_tokens": 10},
        "cost_usd": 0,
        "retrieval_ms": 5,
        "generation_ms": 10,
    }

    def invoke(data):
        question = data["question"].lower()
        injection = "html injection" in question
        kwargs["before_embedding"]()
        kwargs["checkpoint"](
            {
                "evidence": [
                    {
                        "label": "S1",
                        "document_id": str(uuid4()),
                        "filename": "<img src=x onerror=alert(1)>"
                        if injection
                        else "Fixture guide.txt",
                        "page_number": 1,
                        "rank": 1,
                        "text": "<script>alert(1)</script>"
                        if injection
                        else "The fixture answer is forty-two.",
                    }
                ]
            }
        )
        kwargs["before_generation"]()
        time.sleep(16 if "slow response" in question else 0.3)
        if "fail provider" in question:
            raise RuntimeError("Deterministic provider failure")
        answer = (
            "INSUFFICIENT_EVIDENCE"
            if "unanswerable" in question
            else "<img src=x onerror=alert(1)> [S1]"
            if injection
            else "The fixture answer is forty-two. [S1]"
        )
        return {"answer": answer, "finish_reason": "stop"}

    return SimpleNamespace(invoke=invoke), SimpleNamespace(updates=updates)


def worker_loop():
    deployed_answers.compile_answer_chain = fake_chain
    while True:
        with Session(engine) as session:
            ids = session.scalars(
                select(DeployedAnswerRun.id)
                .where(DeployedAnswerRun.status == "queued")
                .limit(5)
            ).all()
        for run_id in ids:
            deployed_answers.process_deployed(run_id, engine)
        time.sleep(0.15)


if __name__ == "__main__":
    import uvicorn

    seed()
    threading.Thread(target=worker_loop, daemon=True).start()
    from app.main import app

    uvicorn.run(app, host="127.0.0.1", port=8000, access_log=False, log_level="warning")
