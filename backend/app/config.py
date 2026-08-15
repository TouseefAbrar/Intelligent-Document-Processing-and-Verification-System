"""Application configuration loaded from environment variables (.env).

The configuration is centralised here so the whole system can be tuned
without touching code. All secrets (Groq API key, DB URL) are read from
the environment and never hard-coded.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App -----------------------------------------------------------------
    APP_NAME: str = "Ezitech Document Intelligence API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    MAX_UPLOAD_SIZE_MB: int = 25

    # --- Secrets --------------------------------------------------------------
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    # Text fallbacks tried in order when the primary is rate-limited / busy.
    # Only models that actually exist on the account should be listed (verified
    # via GET /models). Vision models must never appear here.
    GROQ_FALLBACK_MODELS: list[str] = [
        "llama-3.1-8b-instant",
        "qwen/qwen3.6-27b",
    ]
    # Vision models: left empty unless the account has a Groq vision model.
    # Decommissioned / inaccessible models (e.g. llama-3.2-*-vision-preview)
    # must NOT be listed here or every OCR/fallback call burns a failed request.
    GROQ_VISION_MODEL: str = ""
    GROQ_VISION_MODELS: list[str] = []

    # --- Groq resilience --------------------------------------------------------
    # Max attempts per candidate before giving up on transient (429/5xx) errors.
    GROQ_MAX_RETRIES: int = 2
    # Fail fast for this many seconds after a 429 so the pipeline drops to the
    # deterministic regex/rules layer instead of hammering the API.
    GROQ_RATE_LIMIT_COOLDOWN_SECONDS: int = 300

    # --- Database -------------------------------------------------------------
    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'ezitech.db'}"

    # --- Auth / security --------------------------------------------------------
    JWT_SECRET: str = ""
    TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days
    RESET_TOKEN_EXPIRE_MINUTES: int = 60
    # Public URL of the frontend used to build password-reset links. Falls back
    # to the request Origin (same-origin deployments) automatically.
    FRONTEND_URL: str = ""

    # --- Email / SMTP (for Forgot Password) ------------------------------------
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_FROM_NAME: str = "Verity.AI"
    SMTP_USE_TLS: bool = True

    # --- OCR ------------------------------------------------------------------
    OCR_PROVIDER: str = "auto"  # auto | groq | tesseract | easyocr | pdf
    TESSERACT_CMD: str = "tesseract"
    EASYOCR_LANGS: list[str] = ["en"]
    OCR_MIN_TEXT_LENGTH: int = 20

    # --- Processing ------------------------------------------------------------
    MIN_IMAGE_DPI: int = 120
    BLUR_VARIANCE_THRESHOLD: int = 100
    DUPLICATE_HASH_THRESHOLD: float = 0.90
    # --- Forgery / fake-document detection ------------------------------------
    # Signals at/above RED (strong) can flag/reject a document. Signals below
    # RED are corroborating warnings that never escalate a document on their
    # own — real scans/captures routinely show weak forensic traces.
    FORGERY_YELLOW_THRESHOLD: float = 0.40
    FORGERY_RED_THRESHOLD: float = 0.60
    FORGERY_LLM_ENABLED: bool = True
    COMPLETENESS_REQUIRED_DOCS: list[str] = [
        "resume",
        "cnic",
        "offer_letter",
        "degree",
        "transcript",
    ]

    # --- CORS ------------------------------------------------------------------
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"]

    # --- Storage ----------------------------------------------------------------
    UPLOAD_DIR: Path = BASE_DIR / "app" / "storage" / "uploads"
    PROCESSED_DIR: Path = BASE_DIR / "app" / "storage" / "processed"
    REPORT_DIR: Path = BASE_DIR / "app" / "storage" / "reports"
    DATA_DIR: Path = BASE_DIR / "app" / "storage" / "data"

    # --- Logging -----------------------------------------------------------------
    LOG_LEVEL: str = "INFO"

    @property
    def allowed_extensions(self) -> set[str]:
        return {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}

    @property
    def upload_dir(self) -> Path:
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        return self.UPLOAD_DIR

    @property
    def processed_dir(self) -> Path:
        self.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        return self.PROCESSED_DIR

    @property
    def report_dir(self) -> Path:
        self.REPORT_DIR.mkdir(parents=True, exist_ok=True)
        return self.REPORT_DIR

    @property
    def data_dir(self) -> Path:
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        return self.DATA_DIR

    @property
    def groq_available(self) -> bool:
        key = self.GROQ_API_KEY.strip()
        # Ignore placeholder / unset values so the health probe is truthful.
        if not key or key.lower().startswith("your_") or key.lower() == "changeme":
            return False
        return True

    @property
    def smtp_configured(self) -> bool:
        return bool(self.SMTP_HOST.strip() and self.SMTP_USER.strip() and self.SMTP_PASSWORD.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
