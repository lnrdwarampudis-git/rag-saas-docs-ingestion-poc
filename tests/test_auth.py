import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jwt import PyJWK

from app.auth import jwks as jwks_module
from app.auth.dependencies import get_current_user, require_roles
from app.auth.tokens import TokenValidationError, decode_access_token
from app.config import get_settings

KID = "test-key-1"


@pytest.fixture
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


@pytest.fixture(autouse=True)
def patched_jwks(rsa_keypair, monkeypatch):
    """Points the JWKS cache at our in-memory test keypair instead of a real Keycloak."""
    private_key, public_key = rsa_keypair

    class FakeJWKSCache:
        def get_key(self, kid: str) -> PyJWK:
            if kid != KID:
                raise jwks_module.JWKSFetchError("unknown kid")
            jwk_dict = jwt.algorithms.RSAAlgorithm.to_jwk(public_key, as_dict=True)
            jwk_dict["kid"] = KID
            return PyJWK.from_dict(jwk_dict)

    monkeypatch.setattr("app.auth.tokens.get_jwks_cache", lambda: FakeJWKSCache())
    return private_key


def _sign_token(private_key, overrides: dict | None = None) -> str:
    settings = get_settings()
    now = int(time.time())
    claims = {
        "sub": "user-123",
        "iss": settings.keycloak_issuer,
        "aud": settings.keycloak_audience,
        "iat": now,
        "exp": now + 300,
        "email": "user@example.test",
        "preferred_username": "user123",
        "realm_access": {"roles": ["finance"]},
        "tenant_id": "00000000-0000-4000-8000-000000000001",
    }
    if overrides:
        claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": KID})


def test_decode_access_token_accepts_valid_token(rsa_keypair):
    private_key, _ = rsa_keypair
    token = _sign_token(private_key)
    claims = decode_access_token(token)
    assert claims["sub"] == "user-123"


def test_decode_access_token_rejects_expired_token(rsa_keypair):
    private_key, _ = rsa_keypair
    token = _sign_token(private_key, {"iat": int(time.time()) - 1000, "exp": int(time.time()) - 500})
    with pytest.raises(TokenValidationError):
        decode_access_token(token)


def test_decode_access_token_rejects_wrong_audience(rsa_keypair):
    private_key, _ = rsa_keypair
    token = _sign_token(private_key, {"aud": "some-other-api"})
    with pytest.raises(TokenValidationError):
        decode_access_token(token)


def test_decode_access_token_rejects_wrong_issuer(rsa_keypair):
    private_key, _ = rsa_keypair
    token = _sign_token(private_key, {"iss": "http://evil.example/realms/rag"})
    with pytest.raises(TokenValidationError):
        decode_access_token(token)


def test_decode_access_token_rejects_bad_signature():
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = _sign_token(other_key)  # signed with a key not in the JWKS
    with pytest.raises(TokenValidationError):
        decode_access_token(token)


def _build_test_app() -> FastAPI:
    app = FastAPI()

    @app.get("/whoami")
    def whoami(user=Depends(get_current_user)):
        return {"tenant_id": str(user.tenant_id), "roles": user.roles}

    @app.get("/finance-only")
    def finance_only(user=Depends(require_roles("finance"))):
        return {"ok": True}

    return app


def test_get_current_user_rejects_missing_token():
    client = TestClient(_build_test_app())
    response = client.get("/whoami")
    assert response.status_code == 401


def test_get_current_user_accepts_valid_bearer_token(rsa_keypair):
    private_key, _ = rsa_keypair
    token = _sign_token(private_key)
    client = TestClient(_build_test_app())
    response = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["roles"] == ["finance"]


def test_require_roles_allows_matching_role(rsa_keypair):
    private_key, _ = rsa_keypair
    token = _sign_token(private_key, {"realm_access": {"roles": ["finance"]}})
    client = TestClient(_build_test_app())
    response = client.get("/finance-only", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_require_roles_rejects_missing_role(rsa_keypair):
    private_key, _ = rsa_keypair
    token = _sign_token(private_key, {"realm_access": {"roles": ["support"]}})
    client = TestClient(_build_test_app())
    response = client.get("/finance-only", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
