"""Shared Redis fixed-window budget per OpenRouter key for API and worker calls."""

from redis import Redis, RedisError
from app.core.config import settings
from app.providers import credentials
from app.providers.embeddings import EmbeddingError

SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], 60) end
return count
"""


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
    if count > settings.embedding_requests_per_minute:
        raise EmbeddingError(
            "Local embedding request budget reached. Retry after one minute.",
            transient=True,
        )
