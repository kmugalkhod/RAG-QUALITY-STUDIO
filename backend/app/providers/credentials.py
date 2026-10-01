"""OpenRouter credential bound to the current request or job.

Entry points resolve the stored key for a project's organization and bind it
for the duration of their provider work. Adapters read the bound key. In Clerk
mode an unbound call fails closed instead of using the server environment key.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from uuid import UUID

from pydantic import SecretStr

from app.core.config import settings


class ProviderCredentialMissing(Exception):
    pass


@dataclass(frozen=True)
class ProviderCredential:
    api_key: SecretStr = field(repr=False)
    credential_id: UUID | None  # None: the server environment key.
    scope: str

    @property
    def rate_scope(self) -> str:
        return str(self.credential_id) if self.credential_id else "environment"


@dataclass
class _Binding:
    credential: ProviderCredential | None  # None: the scope has no usable key.
    message: str = ""
    scope: str | None = None
    rejected: bool = False


_binding: ContextVar[_Binding | None] = ContextVar("provider_credential", default=None)

MISSING_ORGANIZATION = (
    "No OpenRouter key is configured for this organization. "
    "Ask an organization admin to add one in Organization settings."
)
MISSING_INSTANCE = (
    "No OpenRouter key is configured. Add one in Organization settings "
    "or set server-side OPENROUTER_API_KEY, then restart backend and workers."
)


def environment_credential() -> ProviderCredential | None:
    if settings.auth_mode == "clerk":
        return None
    value = settings.openrouter_api_key.get_secret_value().strip()
    if not value:
        return None
    return ProviderCredential(SecretStr(value), None, "instance")


@contextmanager
def use(
    credential: ProviderCredential | None,
    message: str = MISSING_INSTANCE,
    scope: str | None = None,
):
    binding = _Binding(credential, message, scope)
    token = _binding.set(binding)
    try:
        yield binding
    finally:
        _binding.reset(token)


def bound() -> _Binding | None:
    return _binding.get()


def current() -> ProviderCredential:
    binding = _binding.get()
    if binding is not None:
        if binding.credential is None:
            raise ProviderCredentialMissing(binding.message)
        return binding.credential
    credential = environment_credential()
    if credential is None:
        raise ProviderCredentialMissing(
            MISSING_ORGANIZATION if settings.auth_mode == "clerk" else MISSING_INSTANCE
        )
    return credential


def report_rejected() -> None:
    """Called by adapters when OpenRouter rejects the bound key (HTTP 401)."""
    binding = _binding.get()
    if binding is not None:
        binding.rejected = True
