# ruff: noqa: F811

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ingestion import IngestionRun, IngestionSchedule
from app.models.pipeline import Pipeline, PipelineVersion
from app.schemas.schedule import DailyCadence, IntervalCadence
from app.services import ingestion
from app.services.schedules import next_due
from app.workers.dispatcher import dispatch_schedules_once
from test_documents import documents_api  # noqa: F401
from test_website_ingestion import save_website, website_api  # noqa: F401


def payload(version, **updates):
    value = {
        "name": "Nightly handbook",
        "pipeline_id": version["pipeline_id"],
        "pipeline_version_id": version["id"],
        "cadence": {"kind": "interval", "minutes": 60},
        "enabled": False,
    }
    value.update(updates)
    return value


def test_schedule_api_defaults_paused_edits_and_runs_exact_version(website_api):  # noqa: F811
    client, engine, project_id, other_id, embedding, _ = website_api
    version = save_website(client, project_id, embedding)
    route = f"/api/projects/{project_id}/ingestion-schedules"
    created = client.post(route, json=payload(version))
    assert created.status_code == 201, created.text
    schedule = created.json()
    assert schedule["status"] == "paused" and schedule["next_run_at"] is None
    assert schedule["pipeline_version_id"] == version["id"]

    assert (
        client.get(
            f"/api/projects/{other_id}/ingestion-schedules/{schedule['id']}"
        ).status_code
        == 404
    )
    enabled = client.post(
        f"{route}/{schedule['id']}",
        json={
            "name": schedule["name"],
            "cadence": schedule["cadence"],
            "enabled": True,
        },
    ).json()
    assert enabled["status"] == "enabled" and enabled["next_run_at"]
    run = client.post(f"{route}/{schedule['id']}/run")
    assert run.status_code == 202, run.text
    assert run.json()["trigger_kind"] == "scheduled"
    assert run.json()["schedule_id"] == schedule["id"]

    with Session(engine) as session:
        answer = Pipeline(
            project_id=UUID(project_id), name="Answer only", kind="answer"
        )
        session.add(answer)
        session.flush()
        answer_version = PipelineVersion(
            pipeline_id=answer.id,
            project_id=answer.project_id,
            version=1,
            name=answer.name,
            execution={},
            layout={},
        )
        session.add(answer_version)
        session.commit()
        answer_id = answer.id
        answer_version_id = answer_version.id
    rejected = client.post(
        route,
        json=payload(
            {"pipeline_id": str(answer_id), "id": str(answer_version_id)},
            name="Wrong kind",
        ),
    )
    assert rejected.status_code == 404


def test_dispatch_due_coalesces_overlap_and_recovers_stale_claim(website_api):  # noqa: F811
    client, engine, project_id, _, embedding, _ = website_api
    version = save_website(client, project_id, embedding)
    route = f"/api/projects/{project_id}/ingestion-schedules"
    schedule = client.post(route, json=payload(version, enabled=True)).json()
    current = datetime.now(UTC)
    with Session(engine) as session:
        row = session.get(IngestionSchedule, UUID(schedule["id"]))
        row.next_run_at = current - timedelta(minutes=1)
        row.claim_token = UUID("11111111-1111-4111-8111-111111111111")
        row.claimed_at = current - timedelta(minutes=2)
        session.commit()

    dispatch_schedules_once(engine, current)
    dispatch_schedules_once(engine, current)
    with Session(engine) as session:
        row = session.get(IngestionSchedule, UUID(schedule["id"]))
        assert row.claim_token is None and row.next_run_at == current + timedelta(
            hours=1
        )
        assert row.last_outcome == "queued"
        assert (
            session.scalar(
                select(func.count())
                .select_from(IngestionRun)
                .where(IngestionRun.schedule_id == row.id)
            )
            == 1
        )
        run = session.get(IngestionRun, row.last_run_id)
        next_due_at = run.created_at + timedelta(microseconds=1)
        next_current = max(datetime.now(UTC), next_due_at + timedelta(seconds=1))
        run.status = "cancelled"
        run.finished_at = next_current
        row.next_run_at = next_due_at
        session.commit()

    dispatch_schedules_once(engine, next_current)
    with Session(engine) as session:
        row = session.get(IngestionSchedule, UUID(schedule["id"]))
        assert (
            session.scalar(
                select(func.count())
                .select_from(IngestionRun)
                .where(IngestionRun.schedule_id == row.id)
            )
            == 2
        )
        assert row.last_run_id is not None and row.last_outcome == "queued"


def test_due_schedule_skips_active_destination_without_partial_run(website_api):  # noqa: F811
    client, engine, project_id, _, embedding, _ = website_api
    version = save_website(client, project_id, embedding)
    active = client.post(
        f"/api/projects/{project_id}/pipelines/{version['pipeline_id']}/versions/{version['id']}/ingestion-runs"
    )
    assert active.status_code == 202
    route = f"/api/projects/{project_id}/ingestion-schedules"
    schedule = client.post(route, json=payload(version, enabled=True)).json()
    current = datetime(2026, 9, 14, 12, tzinfo=UTC)
    with Session(engine) as session:
        row = session.get(IngestionSchedule, UUID(schedule["id"]))
        row.next_run_at = current - timedelta(seconds=1)
        session.commit()
    dispatch_schedules_once(engine, current)
    with Session(engine) as session:
        row = session.get(IngestionSchedule, UUID(schedule["id"]))
        assert row.last_outcome == "skipped"
        assert row.last_error == "A destination run is already active."
        assert (
            session.scalar(
                select(func.count())
                .select_from(IngestionRun)
                .where(IngestionRun.project_id == UUID(project_id))
            )
            == 1
        )


def test_dispatch_recovers_run_created_before_schedule_checkpoint(website_api):  # noqa: F811
    client, engine, project_id, _, embedding, _ = website_api
    version = save_website(client, project_id, embedding)
    route = f"/api/projects/{project_id}/ingestion-schedules"
    schedule = client.post(route, json=payload(version, enabled=True)).json()
    current = datetime.now(UTC)
    with Session(engine) as session:
        row = session.get(IngestionSchedule, UUID(schedule["id"]))
        row.next_run_at = current - timedelta(seconds=1)
        row.claim_token = UUID("22222222-2222-4222-8222-222222222222")
        row.claimed_at = current - timedelta(minutes=2)
        session.commit()
        created = ingestion.start_run(
            session,
            UUID(project_id),
            UUID(version["pipeline_id"]),
            UUID(version["id"]),
            trigger_kind="scheduled",
            schedule_id=row.id,
        )

    dispatch_schedules_once(engine, current)
    with Session(engine) as session:
        row = session.get(IngestionSchedule, UUID(schedule["id"]))
        assert row.last_run_id == created["id"]
        assert row.last_outcome == "queued"
        assert row.claim_token is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(IngestionRun)
                .where(IngestionRun.schedule_id == row.id)
            )
            == 1
        )


def test_dispatch_records_non_http_creation_failure_and_advances(
    website_api, monkeypatch
):  # noqa: F811
    client, engine, project_id, _, embedding, _ = website_api
    version = save_website(client, project_id, embedding)
    route = f"/api/projects/{project_id}/ingestion-schedules"
    schedule = client.post(route, json=payload(version, enabled=True)).json()
    current = datetime(2026, 9, 14, 12, tzinfo=UTC)
    with Session(engine) as session:
        row = session.get(IngestionSchedule, UUID(schedule["id"]))
        row.next_run_at = current - timedelta(seconds=1)
        session.commit()

    def fail_start(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(ingestion, "start_run", fail_start)
    dispatch_schedules_once(engine, current)
    with Session(engine) as session:
        row = session.get(IngestionSchedule, UUID(schedule["id"]))
        assert row.last_outcome == "failed"
        assert row.last_error == "The scheduled run could not be created safely."
        assert row.next_run_at == current + timedelta(hours=1)
        assert row.claim_token is None

    with Session(engine) as session:
        row = session.get(IngestionSchedule, UUID(schedule["id"]))
        row.next_run_at = current - timedelta(seconds=1)
        session.commit()

    def fail_with_other_conflict(*args, **kwargs):
        raise HTTPException(409, "A different configuration validation conflict.")

    monkeypatch.setattr(ingestion, "start_run", fail_with_other_conflict)
    dispatch_schedules_once(engine, current)
    with Session(engine) as session:
        row = session.get(IngestionSchedule, UUID(schedule["id"]))
        assert row.last_outcome == "failed"
        assert row.last_error == "The scheduled run could not be created safely."


def test_dispatch_adopts_run_when_creation_raises_after_commit(
    website_api, monkeypatch
):  # noqa: F811
    client, engine, project_id, _, embedding, _ = website_api
    version = save_website(client, project_id, embedding)
    route = f"/api/projects/{project_id}/ingestion-schedules"
    schedule = client.post(route, json=payload(version, enabled=True)).json()
    schedule_id = UUID(schedule["id"])
    current = datetime.now(UTC)
    with Session(engine) as session:
        row = session.get(IngestionSchedule, schedule_id)
        row.next_run_at = current - timedelta(seconds=1)
        session.commit()

    original = ingestion.start_run

    def create_then_raise(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("lost response after commit")

    monkeypatch.setattr(ingestion, "start_run", create_then_raise)
    dispatch_schedules_once(engine, current)
    with Session(engine) as session:
        row = session.get(IngestionSchedule, schedule_id)
        assert row.last_run_id is not None and row.last_outcome == "queued"
        assert row.last_error is None and row.claim_token is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(IngestionRun)
                .where(IngestionRun.schedule_id == row.id)
            )
            == 1
        )


def test_concurrent_schedule_edit_is_not_overwritten_after_run_creation(
    website_api, monkeypatch
):  # noqa: F811
    client, engine, project_id, _, embedding, _ = website_api
    version = save_website(client, project_id, embedding)
    route = f"/api/projects/{project_id}/ingestion-schedules"
    schedule = client.post(route, json=payload(version, enabled=True)).json()
    schedule_id = UUID(schedule["id"])
    current = datetime.now(UTC)
    edited_due = current + timedelta(hours=2)
    with Session(engine) as session:
        row = session.get(IngestionSchedule, schedule_id)
        row.next_run_at = current - timedelta(seconds=1)
        session.commit()

    original = ingestion.start_run

    def start_and_edit(*args, **kwargs):
        result = original(*args, **kwargs)
        with Session(engine) as concurrent:
            row = concurrent.get(IngestionSchedule, schedule_id)
            row.cadence = {"kind": "interval", "minutes": 120}
            row.next_run_at = edited_due
            row.claim_token = row.claimed_at = None
            concurrent.commit()
        return result

    monkeypatch.setattr(ingestion, "start_run", start_and_edit)
    dispatch_schedules_once(engine, current)
    with Session(engine) as session:
        row = session.get(IngestionSchedule, schedule_id)
        assert row.cadence == {"kind": "interval", "minutes": 120}
        assert row.next_run_at == edited_due
        assert row.last_run_id is not None and row.last_outcome == "queued"


def test_next_due_interval_and_daily_are_timezone_aware_and_coalesced():
    current = datetime(2026, 3, 8, 7, 30, tzinfo=UTC)
    assert next_due(
        IntervalCadence(kind="interval", minutes=15), current
    ) == current + timedelta(minutes=15)
    daily = DailyCadence(kind="daily", local_time="09:00", timezone="America/New_York")
    assert next_due(daily, current) == datetime(2026, 3, 8, 13, 0, tzinfo=UTC)
