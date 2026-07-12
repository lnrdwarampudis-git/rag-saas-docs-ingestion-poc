import hashlib
import json
from typing import Any

from app.config import get_settings

CACHE_SCHEMA_VERSION = "v5"

try:
    from redis import Redis
    from redis.exceptions import RedisError
except ImportError:  # pragma: no cover - exercised when optional dependency is absent
    Redis = None  # type: ignore[assignment]

    class RedisError(Exception):
        pass


class QueryCache:
    def __init__(self, ttl_seconds: int = 900) -> None:
        self.ttl_seconds = ttl_seconds
        self._memory: dict[str, dict[str, Any]] = {}
        self._redis: Any | None = None
        if Redis is None:
            return
        try:
            self._redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
            self._redis.ping()
        except RedisError:
            self._redis = None

    def get(self, key: str) -> dict[str, Any] | None:
        if self._redis is not None:
            try:
                value = self._redis.get(key)
                return json.loads(value) if value else None
            except RedisError:
                return self._memory.get(key)
        return self._memory.get(key)

    def set(self, key: str, value: dict[str, Any]) -> None:
        self._memory[key] = value
        if self._redis is not None:
            try:
                self._redis.setex(key, self.ttl_seconds, json.dumps(value))
            except RedisError:
                return


def cache_key(payload: dict[str, Any]) -> str:
    versioned_payload = {"cache_schema_version": CACHE_SCHEMA_VERSION, **payload}
    encoded = json.dumps(versioned_payload, sort_keys=True).encode("utf-8")
    return "rag:query:" + hashlib.sha256(encoded).hexdigest()
