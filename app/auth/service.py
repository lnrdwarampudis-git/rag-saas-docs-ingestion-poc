"""Resolves an AuthenticatedUser from validated Keycloak token claims.

Postgres (tenants / app_users / roles / user_roles) is the source of truth
for tenant membership and RBAC, per the architecture doc. If the database is
unreachable, we fall back to a `tenant_id` custom claim and `realm_access`
roles baked into the token by Keycloak protocol mappers, so the POC keeps
working without a live DB connection -- but DB-resolved roles always win
when available, since they can be revoked/changed without waiting for a
token to expire.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.models import AuthenticatedUser

logger = logging.getLogger(__name__)

KNOWN_ROLES = {"admin", "finance", "engineering", "legal", "support"}


class UnresolvableIdentityError(Exception):
    """Raised when we can't determine which tenant a token belongs to at all."""


def resolve_authenticated_user(claims: dict, db: Session) -> AuthenticatedUser:
    subject = claims.get("sub")
    if not subject:
        raise UnresolvableIdentityError("Token has no 'sub' claim")

    db_result = _resolve_from_database(subject, db)
    if db_result is not None:
        return db_result

    return _resolve_from_token_claims(subject, claims)


def _resolve_from_database(subject: str, db: Session) -> AuthenticatedUser | None:
    try:
        row = db.execute(
            text(
                """
                SELECT u.id AS app_user_id, u.tenant_id, u.email, u.display_name, u.is_active
                FROM app_users u
                WHERE u.keycloak_subject = :subject
                """
            ),
            {"subject": subject},
        ).mappings().first()

        if row is None or not row["is_active"]:
            return None

        role_rows = db.execute(
            text(
                """
                SELECT r.name
                FROM roles r
                JOIN user_roles ur ON ur.role_id = r.id
                WHERE ur.user_id = :user_id
                """
            ),
            {"user_id": row["app_user_id"]},
        ).mappings()
        roles = sorted({r["name"] for r in role_rows})

        return AuthenticatedUser(
            keycloak_subject=subject,
            tenant_id=row["tenant_id"],
            roles=roles,
            email=row["email"],
            username=row["display_name"],
            app_user_id=row["app_user_id"],
            source="database",
        )
    except SQLAlchemyError:
        logger.warning("RBAC database lookup failed; falling back to token claims", exc_info=True)
        return None


def _resolve_from_token_claims(subject: str, claims: dict) -> AuthenticatedUser:
    raw_tenant_id = claims.get("tenant_id")
    if not raw_tenant_id:
        raise UnresolvableIdentityError(
            "No app_users record and no 'tenant_id' claim on the token"
        )
    try:
        tenant_id = UUID(str(raw_tenant_id))
    except ValueError as exc:
        raise UnresolvableIdentityError("Token 'tenant_id' claim is not a valid UUID") from exc

    realm_roles = set(claims.get("realm_access", {}).get("roles", []))
    roles = sorted(realm_roles.intersection(KNOWN_ROLES))

    return AuthenticatedUser(
        keycloak_subject=subject,
        tenant_id=tenant_id,
        roles=roles,
        email=claims.get("email"),
        username=claims.get("preferred_username"),
        app_user_id=None,
        source="token-claims",
    )
