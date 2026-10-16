"""Recommended source settings: submission, reads, cancellation, limits and
the provenance a saved pipeline version records (spec 0011)."""

import hashlib
import json
from datetime import timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.connectors.safe_http import url_origin
from app.core.config import settings
from app.models.setting_recommendation import SettingRecommendation
from app.schemas.ingestion import IngestionExecution, WebsiteConfig
from app.schemas.setting_recommendations import SettingRecommendationRequest
from app.services.documents import project
from app.services.website_recommendation import (
    MANAGED_PATHS,
    PROBE_VERSION,
    RULES_VERSION,
)
from app.workers.processing import now

ACTIVE = ("queued", "running")
TERMINAL = ("succeeded", "failed", "cancelled")
RETAIN_TERMINAL_PER_PROJECT = 50
RECOMMENDATION_TTL = timedelta(hours=24)
RATE_WINDOW = timedelta(hours=1)
MAX_PROVENANCE_BYTES = 64 * 1024
# A recorded value larger than this is replaced by a marker in provenance, so
# a long URL list cannot push a version past the size bound.
MAX_PROVENANCE_VALUE_BYTES = 4 * 1024


def capability() -> dict:
    return {
        "enabled": settings.setting_recommendations_enabled,
        "page_ceiling": settings.setting_recommendations_page_ceiling,
    }


def _encoded(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def inputs_for(request: SettingRecommendationRequest) -> tuple[dict, str]:
    selection = request.selection.model_dump(mode="json")
    inputs = {
        "selection": selection,
        "entered_url": selection.get("start_url")
        or selection.get("url")
        or selection.get("sitemap_url")
        or (selection.get("urls") or [None])[0],
        "other_sources_max_pages": request.other_sources_max_pages,
        "page_ceiling": settings.setting_recommendations_page_ceiling,
    }
    digest = hashlib.sha256(
        _encoded(
            {
                "target": request.target,
                "selection": selection,
                "other_sources_max_pages": request.other_sources_max_pages,
                "page_ceiling": settings.setting_recommendations_page_ceiling,
                "probe_version": PROBE_VERSION,
                "rules_version": RULES_VERSION,
            }
        ).encode("utf-8")
    ).hexdigest()
    return inputs, digest


def _expired(row: SettingRecommendation) -> bool:
    return row.status in TERMINAL and row.expires_at <= now()


EVIDENCE_KEYS = (
    "requests",
    "robots",
    "extra_robots",
    "start_page",
    "sitemap",
    "links",
    "sections",
    "sample_pages",
    "url_list",
    "timing",
    "warnings",
)


def _evidence(signals: dict) -> dict:
    return {key: signals[key] for key in EVIDENCE_KEYS if key in signals}


def _read(row: SettingRecommendation) -> dict:
    return {
        "id": row.id,
        "source_node_id": row.source_node_id,
        "target": row.target,
        "status": "expired" if _expired(row) else row.status,
        "progress": row.progress,
        "progress_step": row.progress_step,
        "error": row.error,
        "inputs": row.inputs,
        "probe_version": row.probe_version,
        "rules_version": row.rules_version,
        "recommended": row.recommended,
        "fields": row.fields or [],
        "warnings": row.warnings or [],
        "evidence": _evidence(row.signals or {}),
        "created_at": row.created_at,
        "finished_at": row.finished_at,
        "expires_at": row.expires_at,
    }


def start(session: Session, project_id: UUID, request: SettingRecommendationRequest):
    if not settings.setting_recommendations_enabled:
        raise HTTPException(
            503, "Setting recommendations are turned off on this server."
        )
    project(session, project_id)
    inputs, digest = inputs_for(request)
    current = now()
    if not request.refresh:
        # Same node as well as the same inputs, so provenance maps each saved
        # recommendation to exactly one source node.
        cached = session.scalar(
            select(SettingRecommendation)
            .where(
                SettingRecommendation.project_id == project_id,
                SettingRecommendation.source_node_id == request.source_node_id,
                SettingRecommendation.inputs_hash == digest,
                SettingRecommendation.status == "succeeded",
                SettingRecommendation.created_at > current - RECOMMENDATION_TTL,
            )
            .order_by(
                SettingRecommendation.created_at.desc(),
                SettingRecommendation.id.desc(),
            )
            .limit(1)
        )
        if cached is not None:
            return _read(cached)
    recent = session.scalar(
        select(func.count())
        .select_from(SettingRecommendation)
        .where(
            SettingRecommendation.project_id == project_id,
            SettingRecommendation.created_at > current - RATE_WINDOW,
        )
    )
    if recent >= settings.setting_recommendations_per_project_hour:
        raise HTTPException(
            429, "Analysis limit reached for this project. Try again later."
        )
    # One active analysis per source node: a new request replaces the old one.
    session.execute(
        update(SettingRecommendation)
        .where(
            SettingRecommendation.project_id == project_id,
            SettingRecommendation.source_node_id == request.source_node_id,
            SettingRecommendation.status.in_(ACTIVE),
        )
        .values(
            status="cancelled",
            execution_token=None,
            error="Replaced by a newer analysis of this source.",
            updated_at=func.now(),
            finished_at=func.now(),
        )
    )
    retained = session.scalars(
        select(SettingRecommendation.id)
        .where(
            SettingRecommendation.project_id == project_id,
            SettingRecommendation.status.in_(TERMINAL),
        )
        .order_by(
            SettingRecommendation.created_at.desc(), SettingRecommendation.id.desc()
        )
        .offset(RETAIN_TERMINAL_PER_PROJECT)
    ).all()
    if retained:
        session.execute(
            delete(SettingRecommendation).where(SettingRecommendation.id.in_(retained))
        )
    row = SettingRecommendation(
        project_id=project_id,
        target=request.target,
        source_node_id=request.source_node_id,
        inputs=inputs,
        inputs_hash=digest,
        probe_version=PROBE_VERSION,
        rules_version=RULES_VERSION,
        expires_at=current + RECOMMENDATION_TTL,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _read(row)


def get(session: Session, project_id: UUID, recommendation_id: UUID):
    row = session.scalar(
        select(SettingRecommendation).where(
            SettingRecommendation.id == recommendation_id,
            SettingRecommendation.project_id == project_id,
        )
    )
    if row is None:
        raise HTTPException(404, "Recommendation not found in this project.")
    return row


def read(session: Session, project_id: UUID, recommendation_id: UUID):
    return _read(get(session, project_id, recommendation_id))


def cancel(session: Session, project_id: UUID, recommendation_id: UUID):
    row = get(session, project_id, recommendation_id)
    if row.status not in ACTIVE:
        return _read(row)
    session.execute(
        update(SettingRecommendation)
        .where(
            SettingRecommendation.id == row.id,
            SettingRecommendation.status.in_(ACTIVE),
        )
        .values(
            status="cancelled",
            execution_token=None,
            error="Cancelled. A request already sent may finish, but its result is not used.",
            updated_at=func.now(),
            finished_at=func.now(),
        )
    )
    session.commit()
    session.refresh(row)
    return _read(row)


def _comparable(path: str, value):
    if value is None:
        return None
    if path == "allowed_origins":
        return sorted({url_origin(str(item)) for item in value})
    if path in ("include_path_prefixes", "exclude_path_prefixes"):
        return sorted(set(value))
    if path == "requests_per_second":
        return float(value)
    return value


def _bounded(value):
    if len(_encoded(value).encode("utf-8")) > MAX_PROVENANCE_VALUE_BYTES:
        return {"omitted": "Value too large to record."}
    return value


def _node_provenance(row: SettingRecommendation, config: WebsiteConfig) -> dict:
    saved = config.model_dump(mode="json")
    recommended = row.recommended or {}
    by_path = {item["path"]: item for item in row.fields or []}
    fields = {}
    for path in MANAGED_PATHS:
        item = by_path.get(path)
        if item is None or path not in recommended:
            continue
        equal = _comparable(path, saved.get(path)) == _comparable(
            path, recommended.get(path)
        )
        entry = {
            "basis": item["basis"] if equal else "user",
            "recommended": _bounded(_comparable(path, recommended.get(path))),
            "rationale_code": item["rationale_code"],
            "rationale": item["rationale"],
        }
        if not equal:
            entry["saved"] = _bounded(_comparable(path, saved.get(path)))
        fields[path] = entry
    return {
        "target": row.target,
        "recommendation_id": str(row.id),
        "entered_url": (row.inputs or {}).get("entered_url"),
        "analysed_at": (row.finished_at or row.created_at).isoformat(),
        "probe_version": row.probe_version,
        "rules_version": row.rules_version,
        "fields": fields,
    }


def provenance_for_save(
    session: Session,
    project_id: UUID,
    execution: IngestionExecution,
    recommendation_ids: list[UUID],
) -> dict | None:
    """Provenance for a new version; never raises for an unusable ID.

    Each ID is loaded with its project, so a foreign or missing ID is skipped.
    A row of this project that did not succeed is recorded as unavailable for
    its node. `execution` is not read for anything but comparison.
    """
    if not recommendation_ids:
        return None
    rows = session.scalars(
        select(SettingRecommendation)
        .where(
            SettingRecommendation.id.in_(list(dict.fromkeys(recommendation_ids))[:5]),
            SettingRecommendation.project_id == project_id,
        )
        .order_by(SettingRecommendation.created_at, SettingRecommendation.id)
    ).all()
    websites = {
        node.id: node.config
        for node in execution.nodes
        if node.type == "source" and node.config.kind == "website"
    }
    nodes = {}
    for row in rows:
        if row.source_node_id not in websites:
            continue
        if row.status != "succeeded" or not row.recommended:
            nodes[row.source_node_id] = {"status": "recommendation_unavailable"}
            continue
        nodes[row.source_node_id] = _node_provenance(row, websites[row.source_node_id])
    if not nodes:
        return None
    value = {"schema_version": 1, "nodes": nodes}
    if len(_encoded(value).encode("utf-8")) > MAX_PROVENANCE_BYTES:
        # Keep bases and reasons; drop the recorded values first.
        for node in nodes.values():
            for entry in node.get("fields", {}).values():
                entry.pop("recommended", None)
                entry.pop("saved", None)
    return value
