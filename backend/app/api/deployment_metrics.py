"""Loopback-only, bounded-label metrics for deployed answer operations."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import _loopback_request
from app.core.config import settings
from app.db.session import get_session

router = APIRouter(prefix="/api/ops")


@router.get("/deployed-answers/metrics", response_class=PlainTextResponse)
def metrics(request: Request, session: Session = Depends(get_session)):
    if not _loopback_request(request):
        raise HTTPException(403, "Operator metrics are restricted to loopback.")
    if not settings.deployed_answers_enabled:
        raise HTTPException(503, "Deployed answers are disabled.")
    counts = dict(
        session.execute(
            text("SELECT status, count(*) FROM deployed_answer_runs GROUP BY status")
        ).all()
    )
    queue_age = session.scalar(
        text(
            "SELECT COALESCE(EXTRACT(EPOCH FROM (now() - min(created_at))), 0) "
            "FROM deployed_answer_runs WHERE status = 'queued'"
        )
    )
    unknown = session.scalar(
        text(
            "SELECT count(*) FROM deployed_answer_runs "
            "WHERE error_code = 'provider_outcome_unknown'"
        )
    )
    stale = session.scalar(
        text(
            "SELECT count(*) FROM deployed_answer_runs "
            "WHERE status IN ('running','cancel_requested') "
            "AND (deadline_at < now() OR heartbeat_at < now() - interval '130 seconds')"
        )
    )
    day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    spend = session.execute(
        text(
            "SELECT COALESCE(sum(reserved_usd), 0), COALESCE(sum(settled_usd), 0) "
            "FROM deployment_usage_buckets WHERE period = 'day' AND period_start = :day"
        ),
        {"day": day},
    ).one()
    lines = [
        "# HELP rqs_deployed_answer_runs Current durable runs by state.",
        "# TYPE rqs_deployed_answer_runs gauge",
    ]
    for state in (
        "queued",
        "running",
        "cancel_requested",
        "succeeded",
        "insufficient_evidence",
        "failed",
        "cancelled",
    ):
        lines.append(
            f'rqs_deployed_answer_runs{{status="{state}"}} {counts.get(state, 0)}'
        )
    lines.extend(
        [
            "# TYPE rqs_deployed_answer_oldest_queue_seconds gauge",
            f"rqs_deployed_answer_oldest_queue_seconds {float(queue_age):.3f}",
            "# TYPE rqs_deployed_answer_stale_leases gauge",
            f"rqs_deployed_answer_stale_leases {stale}",
            "# TYPE rqs_deployed_answer_unknown_provider_outcomes gauge",
            f"rqs_deployed_answer_unknown_provider_outcomes {unknown}",
            "# TYPE rqs_deployed_answer_reserved_usd gauge",
            f"rqs_deployed_answer_reserved_usd {spend[0]}",
            "# TYPE rqs_deployed_answer_settled_usd gauge",
            f"rqs_deployed_answer_settled_usd {spend[1]}",
        ]
    )
    return "\n".join(lines) + "\n"
