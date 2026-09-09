"""Shared Redis fixed-window budget for API and worker embedding calls."""

from redis import Redis, RedisError
from app.core.config import settings
from app.providers.embeddings import EmbeddingError

SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], 60) end
return count
"""


def reserve_request():
    try:
        with Redis.from_url(
            settings.redis_url, socket_connect_timeout=2, socket_timeout=2
        ) as redis:
            count = redis.eval(SCRIPT, 1, "rag:embedding:requests")
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
