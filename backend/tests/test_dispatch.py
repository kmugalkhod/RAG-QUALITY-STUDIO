from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import ProcessingRun
from app.models.project import Project
from app.workers.celery_app import DEFAULT_QUEUE, LONG_QUEUE, celery
from app.workers.dispatcher import dispatch_once
from app.workers.ingestion import queue_for
from test_documents import documents_api, start, upload  # noqa: F401


def test_long_running_work_uses_its_own_queue():
    def route(name):
        return celery.amqp.router.route({}, name)["queue"].name

    assert route("preview.sources") == route("experiments.step") == LONG_QUEUE
    assert route("documents.process") == route("indexes.embed") == DEFAULT_QUEUE
    assert route("ingestion.coordinate") == DEFAULT_QUEUE
    assert {queue_for(kind) for kind in ("website", "s3", "notion", "confluence")} == {
        LONG_QUEUE
    }
    assert queue_for("existing_files") == queue_for(None) == DEFAULT_QUEUE


def queued_runs(client, project, count):
    return [
        UUID(
            start(client, project, upload(client, project, f"text {i}".encode())["id"])[
                "id"
            ]
        )
        for i in range(count)
    ]


def test_dispatcher_takes_turns_across_organizations(documents_api, monkeypatch):  # noqa: F811
    client, engine, p, q = documents_api
    monkeypatch.setattr(settings, "dispatch_org_concurrency", 2)
    with Session(engine) as session:
        for project, org in ((p, "org_fair_a"), (q, "org_fair_b")):
            session.execute(
                update(Project)
                .where(Project.id == UUID(project))
                .values(organization_id=org)
            )
        session.commit()
    large = queued_runs(client, p, 5)
    small = queued_runs(client, q, 1)

    def dispatched():
        sent = []
        dispatch_once(engine, send=sent.append)
        return [id for id in sent if id in large + small]

    # Each organization's oldest job goes first, and the large upload stops
    # at its cap instead of filling the queue ahead of the small one.
    assert dispatched() == [large[0], small[0], large[1]]
    assert dispatched() == []
    with Session(engine) as session:
        session.execute(
            update(ProcessingRun)
            .where(ProcessingRun.id == large[0])
            .values(status="succeeded")
        )
        session.commit()
    assert dispatched() == [large[2]]
