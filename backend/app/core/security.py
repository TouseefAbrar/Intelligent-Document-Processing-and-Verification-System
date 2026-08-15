"""Password hashing + signed auth tokens.

Implemented with the standard library only (PBKDF2-HMAC-SHA256 for password
hashing, HMAC-signed base64url tokens for sessions) so no extra dependencies
are needed and passwords are never stored in plain text.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from app.config import settings

_PBKDF2_ITERATIONS = 260_000


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + pad)


# --- Passwords -----------------------------------------------------------------

def hash_password(password: str) -> str:
    """Return a salted PBKDF2 hash in ``pbkdf2_sha256$iterations$salt$hash`` form."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${_b64e(salt)}${_b64e(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, expected = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), _b64d(salt), int(iterations))
        return hmac.compare_digest(_b64e(digest), expected)
    except Exception:  # malformed hash never matches
        return False


# --- Signed session tokens -----------------------------------------------------

def _secret() -> bytes:
    secret = settings.JWT_SECRET.strip()
    if not secret:
        # Deterministic per-deployment fallback so tokens survive restarts
        # even when JWT_SECRET is not configured yet.
        secret = hashlib.sha256((settings.DATABASE_URL + settings.APP_NAME).encode("utf-8")).hexdigest()
    return secret.encode("utf-8")


def create_access_token(user_id: int) -> str:
    payload = {"uid": user_id, "exp": int(time.time()) + settings.TOKEN_EXPIRE_MINUTES * 60}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = _b64e(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_access_token(token: str) -> int | None:
    """Return the user id if the token is valid and not expired, else None."""
    try:
        body, sig = token.rsplit(".", 1)
        expected = _b64e(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, sig):
            return None
        payload = json.loads(_b64d(body))
        if int(payload.get("exp", 0)) < time.time():
            return None
        return int(payload["uid"])
    except Exception:
        return None


# --- One-time password-reset tokens --------------------------------------------

def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Only the hash of a reset token is stored in the database."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
