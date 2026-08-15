"""SQLAlchemy ORM models for the Document Intelligence system."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    """A single uploaded document and everything learned about it."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    file_name: Mapped[str] = mapped_column(String(255), index=True)
    stored_path: Mapped[str] = mapped_column(String(500))
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    mime_type: Mapped[str] = mapped_column(String(120), default="")
    extension: Mapped[str] = mapped_column(String(20), default="")
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0)

    ocr_provider: Mapped[str] = mapped_column(String(40), default="")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    ocr_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    language: Mapped[str] = mapped_column(String(20), default="en")

    # Classification
    doc_type: Mapped[str] = mapped_column(String(50), index=True, default="unknown")
    expected_doc_type: Mapped[str] = mapped_column(String(50), default="", index=True)
    classification_confidence: Mapped[float] = mapped_column(Float, default=0.0)

    # Extracted structured data (Pydantic model dumped to JSON)
    extracted: Mapped[dict] = mapped_column(JSON, default=dict)

    # Verification
    quality: Mapped[dict] = mapped_column(JSON, default=dict)      # blur, brightness, laplacian variance
    duplicate: Mapped[dict] = mapped_column(JSON, default=dict)    # group hash, is_duplicate
    verification: Mapped[dict] = mapped_column(JSON, default=dict) # issues, status, scores
    forgery: Mapped[dict] = mapped_column(JSON, default=dict)      # forensic / fake-doc signals
    phash: Mapped[str] = mapped_column(String(64), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    submission_id: Mapped[int | None] = mapped_column(ForeignKey("submissions.id"), nullable=True, index=True)
    submission: Mapped["Submission | None"] = relationship(back_populates="documents")

    @property
    def verification_status(self) -> str:
        return self.verification.get("status", "PENDING")


class Submission(Base):
    """A logical applicant submission grouping one or more documents."""

    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    applicant_ref: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(40), default="PROCESSING", index=True)

    completeness_score: Mapped[float] = mapped_column(Float, default=0.0)
    overall_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    missing_documents: Mapped[list] = mapped_column(JSON, default=list)
    duplicate_documents: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)

    report_path: Mapped[str] = mapped_column(String(500), default="")
    report_data: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    documents: Mapped[list[Document]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )
