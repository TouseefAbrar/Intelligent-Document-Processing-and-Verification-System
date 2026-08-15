"""Pydantic request/response schemas for the public API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    app: str
    version: str
    groq_connected: bool
    ocr_provider: str


class DocumentSummary(BaseModel):
    id: int
    file_name: str
    doc_type: str
    expected_doc_type: str = ""
    classification_confidence: float
    ocr_confidence: float
    verification_status: str
    language: str
    file_size: int


class DocumentDetail(DocumentSummary):
    extracted: dict[str, Any]
    quality: dict[str, Any]
    duplicate: dict[str, Any]
    verification: dict[str, Any]
    forgery: dict[str, Any] = Field(default_factory=dict)
    ocr_provider: str
    raw_text_preview: str = ""
    created_at: datetime


class SubmissionResponse(BaseModel):
    id: int
    applicant_ref: str
    status: str
    completeness_score: float
    overall_confidence: float
    missing_documents: list[str]
    duplicate_documents: list[str]
    summary: dict[str, Any]
    report_url: str = ""
    documents: list[DocumentSummary] = []
    created_at: datetime


class SubmissionDetail(SubmissionResponse):
    documents: list[DocumentDetail] = []


class ReportResponse(BaseModel):
    submission_id: int
    report_path: str
    report_url: str
    format: str


class AnalysisRequest(BaseModel):
    applicant_ref: str = Field(default="", description="Optional applicant reference")
    required_docs: list[str] = Field(
        default=["resume", "cnic", "degree", "transcript"],
        description="Document types required for completeness scoring",
    )


class ErrorResponse(BaseModel):
    detail: str


class ProcessingResult(BaseModel):
    submission: SubmissionResponse
    detail: SubmissionDetail
