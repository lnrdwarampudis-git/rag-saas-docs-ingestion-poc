from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.main import app


def make_user(tenant_id: str, roles: list[str], subject: str = "test-subject") -> AuthenticatedUser:
    return AuthenticatedUser(
        keycloak_subject=subject,
        tenant_id=UUID(tenant_id),
        roles=roles,
        email=f"{subject}@example.test",
        username=subject,
        source="token-claims",
    )


@pytest.fixture
def api_client_as():
    """Returns a factory: api_client_as(tenant_id, roles, subject) -> TestClient
    that bypasses real JWT validation and injects a fixed AuthenticatedUser,
    the same way you'd fake auth in any FastAPI test suite.
    """

    def _make(tenant_id: str, roles: list[str], subject: str = "test-subject") -> TestClient:
        app.dependency_overrides[get_current_user] = lambda: make_user(tenant_id, roles, subject)
        return TestClient(app)

    yield _make
    app.dependency_overrides.pop(get_current_user, None)
