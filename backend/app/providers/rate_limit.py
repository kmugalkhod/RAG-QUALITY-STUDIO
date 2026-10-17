"""Shared Redis fixed-window budget per OpenRouter key for API and worker calls."""

from contextlib import contextmanager
from contextvars import ContextVar

from redis import Redis, RedisError
from app.core.config import settings
from app.providers import credentials
from app.providers.embeddings import EmbeddingError

SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], 60) end
return count
"""


# The share of the per-minute budget a caller may use. Indexing sets 0.75, so
# background work stops at 45 of 60 requests and leaves the rest for queries
# (spec 0012 D7). Both count against one shared window.
_share: ContextVar[float] = ContextVar("embedding_request_share", default=1.0)


@contextmanager
def request_share(share: float):
    token = _share.set(share)
    try:
        yield
    finally:
        _share.reset(token)


def _budget_key() -> str:
    try:
        scope = credentials.current().rate_scope
    except credentials.ProviderCredentialMissing:
        scope = "unbound"
    return f"rag:openrouter:{scope}:requests"


def reserve_request():
    key = _budget_key()
    try:
        with Redis.from_url(
            settings.redis_url, socket_connect_timeout=2, socket_timeout=2
        ) as redis:
            count = redis.eval(SCRIPT, 1, key)
    except RedisError:
        raise EmbeddingError(
            "Embedding rate limiter unavailable. Restore Redis and retry.",
            transient=True,
        ) from None
    if count > int(settings.embedding_requests_per_minute * _share.get()):
        raise EmbeddingError(
            "Local embedding request budget reached. Retry after one minute.",
            throttled=True,
        )
