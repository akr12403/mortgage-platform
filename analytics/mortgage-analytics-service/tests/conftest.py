"""Shared test setup: a test-only JWT secret and a helper that mints tokens like mortgage-service does."""
import os
import time

import jwt

TEST_JWT_SECRET = "test-only-jwt-secret-0123456789-abcdefghijklmnop"
os.environ.setdefault("JWT_SECRET", TEST_JWT_SECRET)
os.environ.setdefault("JWT_ISSUER", "capstone-mortgage-auth")


def make_token(roles=("ADMIN",), sub="admin@capstone.local", secret=TEST_JWT_SECRET,
               issuer="capstone-mortgage-auth", expires_in=600, **extra):
    now = int(time.time())
    claims = {"sub": sub, "roles": list(roles), "iss": issuer, "iat": now, "exp": now + expires_in, **extra}
    return jwt.encode(claims, secret, algorithm="HS256")


def auth_header(*roles, **kwargs):
    return {"Authorization": f"Bearer {make_token(roles or ('ADMIN',), **kwargs)}"}
