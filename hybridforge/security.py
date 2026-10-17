import hmac
import re
import threading
import time
from collections import OrderedDict

import jwt
from fastapi import HTTPException

from .models import ID_PATTERN, Principal


class Authenticator:
    def __init__(self, settings):
        self.settings = settings
        self.jwks = (
            jwt.PyJWKClient(settings.jwks_url, cache_jwk_set=True, lifespan=300, timeout=5)
            if settings.mode == "production"
            else None
        )

    def authenticate(self, authorization):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "Bearer token required")
        token = authorization[7:]
        if len(token) > 16384:
            raise HTTPException(401, "Invalid token")
        if self.settings.mode == "demo":
            if not hmac.compare_digest(token, self.settings.demo_token):
                raise HTTPException(401, "Invalid token")
            return Principal(
                "demo",
                "demo-user",
                ("engineering",),
                frozenset({"rag:read", "rag:write", "rag:observe"}),
            )
        try:
            key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self.settings.audience,
                issuer=self.settings.issuer,
                options={"require": ["exp", "iat", "sub", "iss", "aud", "tenant_id"]},
            )
            tenant, groups, subject = claims["tenant_id"], claims.get("groups", []), claims["sub"]
            scope = claims.get("scope", "")
            if not isinstance(tenant, str) or not re.fullmatch(ID_PATTERN, tenant):
                raise ValueError("Invalid tenant claim")
            if not isinstance(subject, str) or not subject or len(subject) > 200:
                raise ValueError("Invalid subject")
            if (
                not isinstance(groups, list)
                or len(groups) > 32
                or any(not isinstance(g, str) or not re.fullmatch(ID_PATTERN, g) for g in groups)
                or not isinstance(scope, str)
            ):
                raise ValueError("Invalid authorization claims")
            return Principal(tenant, subject, tuple(groups), frozenset(scope.split()))
        except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
            raise HTTPException(401, "Invalid or expired token") from exc


class RateLimiter:
    """Bounded, process-local fixed-window limiter; gateway owns fleet-wide quotas."""

    def __init__(self, rpm, capacity=10000):
        self.rpm, self.capacity = rpm, capacity
        self.entries, self.lock = OrderedDict(), threading.Lock()

    def check(self, principal):
        now = int(time.monotonic() // 60)
        key = (principal.tenant, principal.subject)
        with self.lock:
            window, count = self.entries.get(key, (now, 0))
            if window != now:
                count = 0
            if count >= self.rpm:
                raise HTTPException(429, "Request quota exceeded", headers={"Retry-After": "60"})
            self.entries[key] = (now, count + 1)
            self.entries.move_to_end(key)
            if len(self.entries) > self.capacity:
                self.entries.popitem(last=False)
