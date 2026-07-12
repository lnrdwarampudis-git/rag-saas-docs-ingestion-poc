from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class AuthenticatedUser(BaseModel):
    """The resolved identity/authorization context for a validated request.

    tenant_id and roles are the source of truth for every RBAC decision made
    downstream (ingestion, retrieval). They are never taken from the request
    body, only from the validated token / Postgres RBAC tables.
    """

    keycloak_subject: str
    tenant_id: UUID
    roles: list[str]
    email: str | None = None
    username: str | None = None
    app_user_id: UUID | None = None
    source: str = "database"  # "database" or "token-claims" (fallback)

    def has_any_role(self, required: set[str]) -> bool:
        if not required:
            return True
        return bool(required.intersection(self.roles))
