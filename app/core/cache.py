import json
import logging
from typing import Any

from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis: Redis | None = None


async def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def cache_get(key: str) -> Any | None:
    """Return parsed JSON value or None on miss / error."""
    try:
        r = await get_redis()
        raw = await r.get(key)
        if raw is None:
            return None
        logger.debug("Cache HIT: %s", key)
        return json.loads(raw)
    except Exception as exc:
        logger.warning("Cache GET failed for %s: %s", key, exc)
        return None


async def cache_set(key: str, value: Any, ttl: int | None = None) -> None:
    """Serialise value to JSON and store with TTL."""
    if ttl is None:
        ttl = settings.cache_ttl_seconds
    try:
        r = await get_redis()
        await r.setex(key, ttl, json.dumps(value))
        logger.debug("Cache SET: %s (TTL=%ds)", key, ttl)
    except Exception as exc:
        logger.warning("Cache SET failed for %s: %s", key, exc)


async def cache_delete(key: str) -> None:
    try:
        r = await get_redis()
        await r.delete(key)
        logger.debug("Cache DELETE: %s", key)
    except Exception as exc:
        logger.warning("Cache DELETE failed for %s: %s", key, exc)