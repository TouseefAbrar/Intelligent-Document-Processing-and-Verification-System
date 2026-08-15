"""Pydantic request/response schemas for authentication."""
from __future__ import annotations

from pydantic import BaseModel, Field

EMAIL_PATTERN = r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$"


class RegisterRequest(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=255)
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=255)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=8, max_length=200)
    new_password: str = Field(min_length=8, max_length=128)


class AuthUserOut(BaseModel):
    name: str
    email: str


class AuthResponse(BaseModel):
    user: AuthUserOut
    token: str


class ForgotPasswordResponse(BaseModel):
    message: str
    reset_sent: bool = True
    # Only populated when SMTP is not configured (development), so the flow
    # remains usable until email credentials are added.
    dev_reset_link: str | None = None


class MessageResponse(BaseModel):
    message: str
