"""Organization chat model approvals and the OpenRouter catalog they come from."""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import httpx
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.config import settings
from app.models.chat_model import ChatModelApproval
from app.providers import chat_models
from app.providers.chat_models import ChatModelOption
from app.services import provider_credentials

# Public endpoint: no key is sent. Only text-output models are requested.
CATALOG_URL = "https://openrouter.ai/api/v1/models?output_modalities=text"
CATALOG_TTL_SECONDS = 6 * 3600
CATALOG_MAX_BYTES = 20_000_000
MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{1,199}$")
PROVIDER = "openrouter"


@dataclass(frozen=True)
class CatalogModel:
    id: str
    name: str
    context_length: int
    prompt_usd_per_mtok: Decimal | None
    completion_usd_per_mtok: Decimal | None


_cache: dict = {"models": None, "fetched_at": None, "expires": 0.0}
_cache_lock = threading.Lock()


def now():
    return datetime.now(UTC)


def _require_manager(principal: Principal):
    if not provider_credentials.can_manage(principal):
        raise HTTPException(403, "Organization admin access is required.")


def _per_million(value) -> Decimal | None:
    """OpenRouter prices are USD per token as strings; negative means variable."""
    try:
        price = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not price.is_finite() or price < 0:
        return None
    return (price * 1_000_000).quantize(Decimal("0.000001"))


def _expired(value) -> bool:
    if not value:
        return False
    try:
        day = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return False
    if day.tzinfo is None:
        day = day.replace(tzinfo=UTC)
    return day <= now()


def parse_catalog(payload) -> list[CatalogModel]:
    """Untrusted provider data: keep only well-formed, current text chat models."""
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("catalog")
    models = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        model_id = row.get("id")
        if not isinstance(model_id, str) or not MODEL_ID.fullmatch(model_id):
            continue
        if "embedding" in model_id.lower() or _expired(row.get("expiration_date")):
            continue
        architecture = row.get("architecture")
        outputs = (
            architecture.get("output_modalities")
            if isinstance(architecture, dict)
            else None
        )
        if isinstance(outputs, list) and "text" not in outputs:
            continue
        context = row.get("context_length")
        if not isinstance(context, int) or isinstance(context, bool) or context < 2048:
            continue
        pricing = row.get("pricing") if isinstance(row.get("pricing"), dict) else {}
        name = row.get("name")
        models[model_id] = CatalogModel(
            id=model_id,
            name=name.strip()[:200]
            if isinstance(name, str) and name.strip()
            else model_id,
            context_length=context,
            prompt_usd_per_mtok=_per_million(pricing.get("prompt")),
            completion_usd_per_mtok=_per_million(pricing.get("completion")),
        )
    return sorted(models.values(), key=lambda m: m.id)


def _fetch(transport=None) -> list[CatalogModel]:
    try:
        with httpx.Client(
            timeout=httpx.Timeout(15, connect=5),
            transport=transport,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            with client.stream("GET", CATALOG_URL) as response:
                if response.status_code != 200:
                    raise ValueError("status")
                body = bytearray()
                for block in response.iter_bytes():
                    body.extend(block)
                    if len(body) > CATALOG_MAX_BYTES:
                        raise ValueError("size")
        return parse_catalog(json.loads(body))
    except (httpx.HTTPError, ValueError):
        raise HTTPException(
            503, "The OpenRouter model catalog is unavailable right now. Retry shortly."
        ) from None


def catalog(transport=None, refresh=False) -> tuple[list[CatalogModel], datetime]:
    with _cache_lock:
        if (
            not refresh
            and _cache["models"] is not None
            and time.monotonic() < _cache["expires"]
        ):
            return _cache["models"], _cache["fetched_at"]
    models = _fetch(transport)
    fetched = now()
    with _cache_lock:
        _cache.update(
            models=models,
            fetched_at=fetched,
            expires=time.monotonic() + CATALOG_TTL_SECONDS,
        )
    return models, fetched


def clear_catalog_cache():
    with _cache_lock:
        _cache.update(models=None, fetched_at=None, expires=0.0)


def _float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def option(row: ChatModelApproval) -> ChatModelOption:
    return ChatModelOption(
        id=row.model_id,
        label=row.label,
        context_tokens=min(row.context_length, settings.chat_context_tokens),
        prompt_usd_per_mtok=_float(row.prompt_usd_per_mtok),
        completion_usd_per_mtok=_float(row.completion_usd_per_mtok),
        catalog_fetched_at=row.catalog_fetched_at,
        source="organization",
        is_default=row.is_default,
    )


def _rows(session: Session, scope_key: str) -> list[ChatModelApproval]:
    return list(
        session.scalars(
            select(ChatModelApproval)
            .where(
                ChatModelApproval.scope_key == scope_key,
                ChatModelApproval.provider == PROVIDER,
            )
            .order_by(ChatModelApproval.is_default.desc(), ChatModelApproval.label)
        )
    )


def approved_for_scope(
    session: Session, scope_key: str | None
) -> list[ChatModelOption]:
    return [option(row) for row in _rows(session, scope_key)] if scope_key else []


def read(session: Session, principal: Principal) -> dict:
    scope_key, _ = provider_credentials.principal_scope(principal)
    approved = approved_for_scope(session, scope_key)
    with chat_models.use(approved):
        models = chat_models.available()
        default = chat_models.default_model(models)
    return {
        "scope": "instance" if scope_key == "instance" else "organization",
        "can_manage": provider_credentials.can_manage(principal),
        "context_ceiling": settings.chat_context_tokens,
        "default_model": default,
        "models": models,
    }


def search(
    session: Session,
    principal: Principal,
    q: str,
    offset: int,
    limit: int,
    transport=None,
) -> dict:
    _require_manager(principal)
    scope_key, _ = provider_credentials.principal_scope(principal)
    approved = {row.model_id for row in _rows(session, scope_key)}
    models, fetched = catalog(transport)
    terms = q.strip().lower().split()
    matches = [
        m
        for m in models
        if all(t in m.id.lower() or t in m.name.lower() for t in terms)
    ]
    return {
        "items": [
            {
                "id": m.id,
                "name": m.name,
                "context_length": m.context_length,
                "prompt_usd_per_mtok": _float(m.prompt_usd_per_mtok),
                "completion_usd_per_mtok": _float(m.completion_usd_per_mtok),
                "approved": m.id in approved,
            }
            for m in matches[offset : offset + limit]
        ],
        "total": len(matches),
        "offset": offset,
        "limit": limit,
        "fetched_at": fetched,
    }


def approve(
    session: Session, principal: Principal, model_id: str, transport=None
) -> dict:
    _require_manager(principal)
    scope_key, organization_id = provider_credentials.principal_scope(principal)
    models, fetched = catalog(transport)
    found = next((m for m in models if m.id == model_id), None)
    if found is None:
        raise HTTPException(
            422, "That model is not an available OpenRouter text model."
        )
    existing = session.scalar(
        select(ChatModelApproval).where(
            ChatModelApproval.scope_key == scope_key,
            ChatModelApproval.provider == PROVIDER,
            ChatModelApproval.model_id == model_id,
        )
    )
    if existing is None:
        first = not _rows(session, scope_key)
        session.add(
            ChatModelApproval(
                scope_key=scope_key,
                organization_id=organization_id,
                provider=PROVIDER,
                model_id=found.id,
                label=found.name,
                context_length=found.context_length,
                prompt_usd_per_mtok=found.prompt_usd_per_mtok,
                completion_usd_per_mtok=found.completion_usd_per_mtok,
                catalog_fetched_at=fetched,
                # The first approval becomes the organization default.
                is_default=first,
                approved_by=principal.subject,
            )
        )
        try:
            session.commit()
        except IntegrityError:
            # A concurrent approval of the same model, or default, won; approval is idempotent.
            session.rollback()
    return read(session, principal)


def remove(session: Session, principal: Principal, model_id: str) -> dict:
    _require_manager(principal)
    scope_key, _ = provider_credentials.principal_scope(principal)
    row = session.scalar(
        select(ChatModelApproval)
        .where(
            ChatModelApproval.scope_key == scope_key,
            ChatModelApproval.provider == PROVIDER,
            ChatModelApproval.model_id == model_id,
        )
        .with_for_update()
    )
    if row is None:
        raise HTTPException(404, "That model is not approved.")
    # Saved pipeline versions keep the model ID; validation flags it until re-approved.
    session.delete(row)
    session.commit()
    return read(session, principal)


def set_default(session: Session, principal: Principal, model_id: str) -> dict:
    _require_manager(principal)
    scope_key, _ = provider_credentials.principal_scope(principal)
    rows = {
        row.model_id: row
        for row in session.scalars(
            select(ChatModelApproval)
            .where(
                ChatModelApproval.scope_key == scope_key,
                ChatModelApproval.provider == PROVIDER,
            )
            .with_for_update()
        )
    }
    if model_id not in rows:
        raise HTTPException(404, "Approve the model before making it the default.")
    session.execute(
        update(ChatModelApproval)
        .where(
            ChatModelApproval.scope_key == scope_key,
            ChatModelApproval.provider == PROVIDER,
            ChatModelApproval.is_default,
        )
        .values(is_default=False, updated_at=now())
    )
    session.flush()
    rows[model_id].is_default = True
    rows[model_id].updated_at = now()
    session.commit()
    return read(session, principal)
