"""Fetches and caches Keycloak's JSON Web Key Set (JWKS).

Keycloak rotates signing keys occasionally (kid changes). We cache the key
set for a short TTL so we don't hit the network on every request, but still
pick up rotated keys without a restart.
"""
from __future__ import annotations

import threading
import time

import httpx
import jwt
from jwt import PyJWK

from app.config import get_settings


class JWKSFetchError(Exception):
    """Raised when the JWKS document cannot be retrieved or parsed."""


class JWKSCache:
    def __init__(self, jwks_url: str, cache_seconds: int = 300) -> None:
        self._jwks_url = jwks_url
        self._cache_seconds = cache_seconds
        self._lock = threading.Lock()
        self._keys_by_kid: dict[str, PyJWK] = {}
        self._fetched_at: float = 0.0

    def get_key(self, kid: str) -> PyJWK:
        if self._is_stale() or kid not in self._keys_by_kid:
            self._refresh()
        try:
            return self._keys_by_kid[kid]
        except KeyError as exc:
            raise JWKSFetchError(f"Signing key '{kid}' not found in JWKS") from exc

    def _is_stale(self) -> bool:
        return (time.monotonic() - self._fetched_at) > self._cache_seconds

    def _refresh(self) -> None:
        with self._lock:
            # Another thread may have refreshed while we waited for the lock.
            if not self._is_stale() and self._keys_by_kid:
                return
            try:
                response = httpx.get(self._jwks_url, timeout=5.0)
                response.raise_for_status()
                jwks_document = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise JWKSFetchError(f"Failed to fetch JWKS from {self._jwks_url}") from exc

            keys_by_kid: dict[str, PyJWK] = {}
            for raw_key in jwks_document.get("keys", []):
                kid = raw_key.get("kid")
                if not kid:
                    continue
                try:
                    keys_by_kid[kid] = PyJWK.from_dict(raw_key)
                except jwt.InvalidKeyError:
                    continue

            if not keys_by_kid:
                raise JWKSFetchError(f"No usable signing keys found at {self._jwks_url}")

            self._keys_by_kid = keys_by_kid
            self._fetched_at = time.monotonic()


_cache: JWKSCache | None = None
_cache_lock = threading.Lock()


def get_jwks_cache() -> JWKSCache:
    """Returns a process-wide singleton JWKS cache built from settings."""
    global _cache
    if _cache is None:
        with _cache_lock:
            if _cache is None:
                settings = get_settings()
                jwks_url = f"{settings.keycloak_internal_issuer}/protocol/openid-connect/certs"
                _cache = JWKSCache(jwks_url, cache_seconds=settings.keycloak_jwks_cache_seconds)
    return _cache


def reset_jwks_cache() -> None:
    """Test hook: forces the next get_jwks_cache() call to rebuild the singleton."""
    global _cache
    with _cache_lock:
        _cache = None
