"""Fenced execution of recommended-settings probes (spec 0011)."""

import logging
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import ConnectorFailure
from app.connectors import website_probe
from app.core.config import settings
from app.db.session import engine
from app.models.setting_recommendation import SettingRecommendation
from app.services.website_recommendation import RecommendationFailed, recommend
from app.workers.celery_app import celery
from app.workers.processing import now

# Unexpected failures are retried once by the dispatcher's stale recovery path;
# a site that answered is never probed again automatically.
MAX_FAILURES = 2


def _locked(session: Session, recommendation_id: UUID):
    return session.scalar(
        select(SettingRecommendation)
        .where(SettingRecommendation.id == recommendation_id)
        .with_for_update()
    )


def _owned(row, token) -> bool:
    return row is not None and row.status == "running" and row.execution_token == token


def process_recommendation(
    recommendation_id: UUID, db_engine=engine, probe=None
) -> None:
    """Claim, probe, compute and record one recommendation.

    Every write after the claim requires this attempt's execution token, so a
    stale or duplicate delivery cannot overwrite a newer attempt or a
    cancellation. `probe(selection, on_step)` replaces the network probe in tests.
    """
    db_engine = db_engine.execution_options(isolation_level="READ COMMITTED")
    token = uuid4()
    with Session(db_engine) as session:
        row = _locked(session, recommendation_id)
        if row is None or row.status != "queued" or row.failures >= MAX_FAILURES:
            return
        row.status = "running"
        row.progress = 5
        row.progress_step = None
        row.attempts += 1
        row.execution_token = token
        row.started_at = row.started_at or now()
        row.updated_at = now()
        row.error = None
        inputs = dict(row.inputs)
        session.commit()

    def on_step(step: str, progress: int) -> None:
        with Session(db_engine) as session:
            row = _locked(session, recommendation_id)
            if not _owned(row, token):
                raise website_probe.ProbeStopped()
            row.progress_step = step
            row.progress = progress
            row.updated_at = now()
            session.commit()

    def finish(**values) -> None:
        with Session(db_engine) as session:
            row = _locked(session, recommendation_id)
            if not _owned(row, token):
                return
            for key, value in values.items():
                setattr(row, key, value)
            row.execution_token = None
            row.updated_at = row.finished_at = now()
            session.commit()

    try:
        if probe is None:
            signals = website_probe.probe_website(
                inputs["selection"],
                on_step=on_step,
                user_agent=settings.website_user_agent,
            )
        else:
            signals = probe(inputs["selection"], on_step)
        on_step("validating", 90)
        result = recommend(signals, inputs, settings)
    except website_probe.ProbeStopped:
        return
    except ConnectorFailure as exc:
        finish(status="failed", error=exc.issue.message[:500])
        return
    except RecommendationFailed as exc:
        finish(status="failed", error=str(exc))
        return
    except Exception:
        logging.warning(
            "Setting recommendation %s failed unexpectedly.", recommendation_id
        )
        with Session(db_engine) as session:
            row = _locked(session, recommendation_id)
            if not _owned(row, token):
                return
            row.failures += 1
            row.execution_token = None
            row.updated_at = now()
            row.error = "The site check was interrupted."
            if row.failures < MAX_FAILURES:
                row.status = "queued"
                row.dispatched_at = None
            else:
                row.status = "failed"
                row.finished_at = now()
            session.commit()
        return
    finish(
        status="succeeded",
        progress=100,
        progress_step="validating",
        signals=signals.as_json(),
        recommended=result.recommended,
        fields=result.fields,
        warnings=result.warnings,
        error=None,
    )


@celery.task(name="recommendations.website", soft_time_limit=150, time_limit=160)
def recommend_website(recommendation_id: str):
    process_recommendation(UUID(recommendation_id))
