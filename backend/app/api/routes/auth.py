"""Authentication endpoints: register, login, session, forgot/reset password.

User accounts live in the shared production database (``DATABASE_URL``), so the
same email + password works from any device or browser.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import (
    create_access_token,
    generate_reset_token,
    hash_password,
    hash_token,
    verify_access_token,
    verify_password,
)
from app.database import get_db
from app.models.user import PasswordReset, User
from app.schemas.auth import (
    AuthResponse,
    AuthUserOut,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
)
from app.services.emailer import send_password_reset_email

router = APIRouter(prefix="/auth", tags=["auth"])

DbSession = Annotated[Session, Depends(get_db)]


def _to_auth_response(user: User) -> AuthResponse:
    return AuthResponse(
        user=AuthUserOut(name=user.name, email=user.email),
        token=create_access_token(user.id),
    )


@router.post("/register", response_model=AuthResponse, status_code=201, summary="Create a new account")
def register(payload: RegisterRequest, db: DbSession) -> AuthResponse:
    email = payload.email.strip().lower()
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists. Sign in instead.")
    user = User(email=email, name=payload.name.strip(), password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return _to_auth_response(user)


@router.post("/login", response_model=AuthResponse, summary="Sign in with email + password")
def login(payload: LoginRequest, db: DbSession) -> AuthResponse:
    email = payload.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    return _to_auth_response(user)


@router.get("/me", response_model=AuthUserOut, summary="Current user for the given session token")
def me(authorization: Annotated[str | None, Header()] = None, db: DbSession = None) -> AuthUserOut:
    token = (authorization or "").removeprefix("Bearer ").strip()
    user_id = verify_access_token(token) if token else None
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status_code=401, detail="Session is invalid or expired. Sign in again.")
    return AuthUserOut(name=user.name, email=user.email)


@router.post("/forgot-password", response_model=ForgotPasswordResponse, summary="Request a password reset link")
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: DbSession) -> ForgotPasswordResponse:
    email = payload.email.strip().lower()
    now = datetime.now(timezone.utc)

    # Purge expired tokens on every request so the table stays small.
    for stale in db.scalars(select(PasswordReset).where(PasswordReset.expires_at < now)).all():
        db.delete(stale)
    db.flush()

    user = db.scalar(select(User).where(User.email == email))
    dev_reset_link: str | None = None
    if user is not None:
        token = generate_reset_token()
        db.add(
            PasswordReset(
                email=email,
                token_hash=hash_token(token),
                expires_at=now + timedelta(minutes=settings.RESET_TOKEN_EXPIRE_MINUTES),
            )
        )
        db.commit()
        base = (settings.FRONTEND_URL or request.headers.get("origin") or str(request.base_url)).rstrip("/")
        reset_url = f"{base}/reset?token={token}"
        if not send_password_reset_email(email, reset_url):
            dev_reset_link = reset_url

    # Generic response — never reveals whether the email is registered.
    return ForgotPasswordResponse(
        message="If that email is registered, a password reset link has been sent.",
        reset_sent=True,
        dev_reset_link=dev_reset_link,
    )


@router.post("/reset-password", response_model=MessageResponse, summary="Set a new password with a reset token")
def reset_password(payload: ResetPasswordRequest, db: DbSession) -> MessageResponse:
    now = datetime.now(timezone.utc)
    record = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == hash_token(payload.token)))
    if record is not None and record.expires_at.tzinfo is None:
        record.expires_at = record.expires_at.replace(tzinfo=timezone.utc)  # SQLite stores naive datetimes
    if record is None or record.used or record.expires_at < now:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired. Request a new one.")
    user = db.scalar(select(User).where(User.email == record.email))
    if user is None:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired. Request a new one.")
    user.password_hash = hash_password(payload.new_password)
    record.used = True
    db.commit()
    return MessageResponse(message="Password updated. Sign in with your new password.")
