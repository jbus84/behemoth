import json

import redis

from .settings import settings

_redis_client = None


def get_redis() -> redis.Redis | None:
    global _redis_client
    if not settings.enable_redis:
        return None
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        _redis_client.ping()
    except redis.RedisError:
        return None
    return _redis_client


def cache_get_position(position_id: str) -> dict | None:
    client = get_redis()
    if client is None:
        return None
    try:
        data = client.get(f"position:{position_id}")
    except redis.RedisError:
        return None
    if not data:
        return None
    if not isinstance(data, (str, bytes, bytearray)):
        return None
    return json.loads(data)


def cache_set_position(position_id: str, payload: dict, ttl: int = 30) -> None:
    client = get_redis()
    if client is None:
        return None
    try:
        client.setex(f"position:{position_id}", ttl, json.dumps(payload, default=str))
    except redis.RedisError:
        return None


def cache_invalidate_position(position_id: str) -> None:
    client = get_redis()
    if client is None:
        return None
    try:
        client.delete(f"position:{position_id}")
    except redis.RedisError:
        return None
