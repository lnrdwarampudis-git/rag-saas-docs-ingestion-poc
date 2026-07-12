"""Validates Keycloak-issued access tokens (RS256 JWTs)."""
from __future__ import annotations

import jwt

from app.auth.jwks import JWKSFetchError, get_jwks_cache
from app.config import get_settings


class TokenValidationError(Exception):
    """Raised for any reason a bearer token should be rejected (maps to 401)."""


def decode_access_token(token: str) -> dict:
    """Validates signature, issuer, audience, and expiry. Returns the token claims.

    Raises TokenValidationError on any failure; callers should turn this into
    an HTTP 401 without leaking which specific check failed.
    """
    settings = get_settings()

    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise TokenValidationError("Malformed token header") from exc

    kid = unverified_header.get("kid")
    if not kid:
        raise TokenValidationError("Token header missing 'kid'")

    try:
        signing_key = get_jwks_cache().get_key(kid)
    except JWKSFetchError as exc:
        raise TokenValidationError("Unable to resolve signing key") from exc

    try:
        claims = jwt.decode(
            token,
            key=signing_key.key,
            algorithms=["RS256"],
            audience=settings.keycloak_audience,
            issuer=settings.keycloak_issuer,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenValidationError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenValidationError("Token failed validation") from exc

    return claims
