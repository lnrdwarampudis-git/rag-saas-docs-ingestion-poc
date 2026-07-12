from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.models import AuthenticatedUser
from app.auth.service import UnresolvableIdentityError, resolve_authenticated_user
from app.auth.tokens import TokenValidationError, decode_access_token
from app.db import get_db

_bearer_scheme = HTTPBearer(auto_error=False, description="Keycloak-issued access token")


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> AuthenticatedUser:
    """Validates the bearer token and resolves tenant/roles for this request.

    Every route that touches tenant-scoped data must depend on this rather
    than reading tenant_id/roles from the request body.
    """
    if credentials is None or not credentials.credentials:
        raise _unauthorized("Missing bearer token")

    try:
        claims = decode_access_token(credentials.credentials)
    except TokenValidationError as exc:
        raise _unauthorized(str(exc)) from exc

    try:
        return resolve_authenticated_user(claims, db)
    except UnresolvableIdentityError as exc:
        raise _unauthorized(str(exc)) from exc


def require_roles(*allowed_roles: str):
    """Dependency factory: 403s unless the caller has at least one of the given roles.

    Usage: Depends(require_roles("admin")) or Depends(require_roles("admin", "finance"))
    """
    required = set(allowed_roles)

    def _check(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if not user.has_any_role(required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {sorted(required)}",
            )
        return user

    return _check
