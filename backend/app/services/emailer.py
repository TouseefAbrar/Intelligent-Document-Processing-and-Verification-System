"""Minimal SMTP emailer for password-reset links.

Credentials come exclusively from environment variables (SMTP_*). If SMTP is
not configured the reset link is logged instead so the flow can still be
exercised in development.
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.config import settings
from app.core.logging import get_logger

logger = get_logger("emailer")


def send_password_reset_email(to_email: str, reset_url: str) -> bool:
    """Send a password-reset email. Returns True when actually emailed.

    When SMTP is not configured the link is logged and False is returned so
    callers can surface a development link to the user.
    """
    if not settings.smtp_configured:
        logger.warning("SMTP not configured — password reset link: %s", reset_url)
        return False

    sender = settings.SMTP_FROM.strip() or settings.SMTP_USER
    message = EmailMessage()
    message["Subject"] = "Reset your Verity.AI password"
    message["From"] = f"{settings.SMTP_FROM_NAME} <{sender}>"
    message["To"] = to_email
    message.set_content(
        "Hello,\n\n"
        "We received a request to reset the password for your Verity.AI account.\n"
        "Open the link below to choose a new password (it expires in 60 minutes):\n\n"
        f"{reset_url}\n\n"
        "If you did not request this, you can safely ignore this email.\n\n"
        "— Verity.AI · EEF IDP Engine"
    )

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
        if settings.SMTP_USE_TLS:
            smtp.starttls()
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(message)
    return True
