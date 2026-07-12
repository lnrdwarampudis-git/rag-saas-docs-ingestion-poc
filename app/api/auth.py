from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.auth.models import AuthenticatedUser
from app.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


class AuthConfigResponse(BaseModel):
    issuer: str
    client_id: str
    realm: str
    authorization_endpoint: str
    token_endpoint: str
    end_session_endpoint: str


@router.get("/config", response_model=AuthConfigResponse)
def auth_config() -> AuthConfigResponse:
    """Public OIDC discovery-lite endpoint so the frontend never hardcodes Keycloak URLs."""
    settings = get_settings()
    issuer = settings.keycloak_issuer
    realm = issuer.rstrip("/").rsplit("/realms/", 1)[-1]
    return AuthConfigResponse(
        issuer=issuer,
        client_id=settings.keycloak_client_id,
        realm=realm,
        authorization_endpoint=f"{issuer}/protocol/openid-connect/auth",
        token_endpoint=f"{issuer}/protocol/openid-connect/token",
        end_session_endpoint=f"{issuer}/protocol/openid-connect/logout",
    )


@router.get("/me", response_model=AuthenticatedUser)
def whoami(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    """Returns the resolved identity (tenant, roles) for the current bearer token."""
    return current_user
