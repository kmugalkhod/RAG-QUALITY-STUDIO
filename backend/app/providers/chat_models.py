"""Chat models available to the current request or job.

Server models come from CHAT_MODEL and CHAT_MODELS. Entry points that bind a
project's provider context (``provider_credentials.bound_for_project``) also
bind the models its organization approved. Generation validates against the
union, so every save, preview, deployment and worker path applies one rule.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.core.config import settings


@dataclass(frozen=True)
class ChatModelOption:
    id: str
    label: str
    # Usable prompt budget: the model's context capped by CHAT_CONTEXT_TOKENS.
    context_tokens: int
    prompt_usd_per_mtok: float | None
    completion_usd_per_mtok: float | None
    catalog_fetched_at: datetime | None
    source: Literal["server", "organization"]
    is_default: bool = False


_approved: ContextVar[tuple[ChatModelOption, ...]] = ContextVar(
    "approved_chat_models", default=()
)


def _is_chat(model_id: str) -> bool:
    return bool(model_id) and "embedding" not in model_id.lower()


def server_models() -> list[ChatModelOption]:
    ids = dict.fromkeys(
        m for m in [settings.chat_model, *settings.chat_models] if _is_chat(m)
    )
    return [
        ChatModelOption(
            id=m,
            label=m,
            context_tokens=settings.chat_context_tokens,
            prompt_usd_per_mtok=None,
            completion_usd_per_mtok=None,
            catalog_fetched_at=None,
            source="server",
            is_default=m == settings.chat_model,
        )
        for m in ids
    ]


def available() -> list[ChatModelOption]:
    """Organization approvals first, then server models not already approved."""
    approved = list(_approved.get())
    seen = {m.id for m in approved}
    return approved + [m for m in server_models() if m.id not in seen]


def default_model(options: list[ChatModelOption]) -> str | None:
    for source in ("organization", "server"):
        for option in options:
            if option.source == source and option.is_default:
                return option.id
    return options[0].id if options else None


def no_models_message() -> str:
    if settings.auth_mode == "clerk":
        return (
            "No chat models are approved for this organization. "
            "Ask an organization admin to approve one in Organization settings."
        )
    if settings.auth_mode == "local":
        return (
            "No chat models are available. Approve one in Organization settings "
            "or set CHAT_MODEL on the server."
        )
    return "Configure CHAT_MODEL with an OpenRouter chat model ID on the server."


@contextmanager
def use(options: list[ChatModelOption]):
    token = _approved.set(tuple(options))
    try:
        yield
    finally:
        _approved.reset(token)
