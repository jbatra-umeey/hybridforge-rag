import time
from dataclasses import replace
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from hybridforge.config import Settings
from hybridforge.security import Authenticator, RateLimiter


def test_production_requires_configuration():
    with pytest.raises(ValueError):
        Settings(mode="production").validate()
    with pytest.raises(ValueError):
        Settings(demo_token="short").validate()


@pytest.fixture
def jwt_auth():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = Settings(
        mode="production",
        issuer="https://identity.example.com",
        audience="rag",
        jwks_url="https://identity.example.com/keys",
    )
    auth = Authenticator(settings)
    auth.jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key())
    )
    claims = {
        "sub": "alice",
        "tenant_id": "acme",
        "groups": ["engineering"],
        "scope": "rag:read",
        "iss": settings.issuer,
        "aud": "rag",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }
    return auth, key, claims


def test_oidc_valid_claims(jwt_auth):
    auth, key, claims = jwt_auth
    p = auth.authenticate("Bearer " + jwt.encode(claims, key, algorithm="RS256"))
    assert p.tenant == "acme" and not p.can_write


@pytest.mark.parametrize(
    "change",
    [
        {"aud": "wrong"},
        {"iss": "https://evil.example"},
        {"exp": 1},
        {"tenant_id": "../other"},
        {"groups": "admin"},
        {"scope": ["rag:write"]},
    ],
)
def test_oidc_rejects_invalid_claims(jwt_auth, change):
    auth, key, claims = jwt_auth
    with pytest.raises(HTTPException) as error:
        auth.authenticate("Bearer " + jwt.encode(claims | change, key, algorithm="RS256"))
    assert error.value.status_code == 401


def test_oidc_rejects_unsigned_token(jwt_auth):
    auth, _, claims = jwt_auth
    with pytest.raises(HTTPException):
        auth.authenticate("Bearer " + jwt.encode(claims, key=None, algorithm="none"))


def test_rate_limit_is_bounded(reader):
    limiter = RateLimiter(1, capacity=2)
    limiter.check(reader)
    with pytest.raises(HTTPException) as error:
        limiter.check(reader)
    assert error.value.status_code == 429
    limiter.check(replace(reader, subject="two"))
    limiter.check(replace(reader, subject="three"))
    assert len(limiter.entries) == 2
