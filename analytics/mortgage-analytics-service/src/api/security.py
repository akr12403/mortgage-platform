"""JWT validation + RBAC for the analytics service (M6 Tasks 6.1/6.2).

Tokens are issued by mortgage-service (POST /api/v1/auth/login) as HS256 JWTs signed with the shared JWT_SECRET.
This module only validates them; it never issues tokens. Errors use the shared envelope via the app's
HTTPException handler: 401 UNAUTHORIZED (no token), 401 INVALID_TOKEN (bad/expired/tampered), 403 ACCESS_DENIED.
Matrix: docs/security/security-controls.md.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ADMIN, UNDERWRITER, SERVICING_AGENT, RISK_ANALYST, SUPPORT = (
    "ADMIN", "UNDERWRITER", "SERVICING_AGENT", "RISK_ANALYST", "SUPPORT")
ALL_ROLES = (ADMIN, UNDERWRITER, SERVICING_AGENT, RISK_ANALYST, SUPPORT)

# Role groups (keep in sync with Rbac.java and the matrix doc)
ANALYTICS_READ = (ADMIN, UNDERWRITER, RISK_ANALYST)
DOCUMENT_UPLOAD = (ADMIN, UNDERWRITER, SERVICING_AGENT)
# Same group as Rbac.BORROWER_PII_READ in mortgage-service: who may see borrower names/contact details.
BORROWER_PII_READ = (ADMIN, UNDERWRITER, SERVICING_AGENT)
# M8 Task 8.4: cached mortgage status/balance by ID (no PII). Everyone who works a loan; not SUPPORT.
LOOKUP_READ = (ADMIN, UNDERWRITER, SERVICING_AGENT, RISK_ANALYST)

MIN_SECRET_BYTES = 32
CLOCK_SKEW_SECONDS = 30

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    subject: str
    roles: tuple[str, ...]


def _secret() -> str:
    secret = os.getenv("JWT_SECRET", "")
    if len(secret.encode("utf-8")) < MIN_SECRET_BYTES:
        raise RuntimeError("JWT_SECRET must be set and at least 32 bytes (256 bits)")
    return secret


def _issuer() -> str:
    return os.getenv("JWT_ISSUER", "capstone-mortgage-auth")


def validate_settings() -> None:
    """Called at startup so a missing/short secret fails fast instead of on the first request."""
    _secret()


def _error(request: Request, status: int, code: str, message: str, headers: dict | None = None) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={
            "code": code,
            "message": message,
            "correlationId": getattr(request.state, "correlation_id", None),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        headers=headers,
    )


def current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _error(request, 401, "UNAUTHORIZED", "Authentication is required", {"WWW-Authenticate": "Bearer"})
    try:
        claims = jwt.decode(
            credentials.credentials,
            _secret(),
            algorithms=["HS256"],  # pinned: never accept "none" or a different algorithm
            issuer=_issuer(),
            leeway=CLOCK_SKEW_SECONDS,
            options={"require": ["exp", "iss", "sub"]},
        )
    except jwt.PyJWTError:
        raise _error(request, 401, "INVALID_TOKEN", "Access token is invalid or expired",
                     {"WWW-Authenticate": 'Bearer error="invalid_token"'})
    roles = claims.get("roles") or []
    if not isinstance(roles, list):
        roles = []
    principal = Principal(subject=str(claims["sub"]), roles=tuple(str(r) for r in roles))
    request.state.user = principal.subject
    return principal


def require_roles(*allowed: str):
    """FastAPI dependency factory: authenticated AND holding at least one of the allowed roles."""
    allowed_set = frozenset(allowed)

    def dependency(request: Request, principal: Principal = Depends(current_principal)) -> Principal:
        if not allowed_set.intersection(principal.roles):
            raise _error(request, 403, "ACCESS_DENIED", "You do not have permission to perform this action")
        return principal

    return dependency
