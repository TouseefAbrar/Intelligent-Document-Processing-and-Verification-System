"""Pre-verification validation gates and canonical status vocabulary.

A document that fails any earlier stage must never be handed to the normal
verification pipeline as a valid document. This module owns:

  * the canonical set of document statuses
  * the mapping of validation-stage failures to user-facing reasons
  * the expected-vs-detected (wrong document) check
  * the tiny "rejected upload" verification record builder

Everything here is pure and deterministic so it can be unit-tested without
network, OCR or a database.
"""
from __future__ import annotations

from app.services.coverage import normalize_doc_type, REJECTED_STATUSES

# Canonical final statuses understood by the UI, analytics and reports.
STATUS_PASSED = "PASSED"
STATUS_FLAGGED = "FLAGGED"
STATUS_FAILED = "FAILED"
STATUS_MISSING = "MISSING"
STATUS_INVALID_FILE_TYPE = "INVALID FILE TYPE"
STATUS_DUPLICATE = "DUPLICATE"
STATUS_BLURRY = "BLURRY"
STATUS_WRONG_DOCUMENT = "WRONG DOCUMENT TYPE"
STATUS_INCONSISTENCY = "INCONSISTENCY DETECTED"
STATUS_FORGERY_DETECTED = "FORGERY DETECTED"

# Statuses that short-circuit the pipeline before rule verification.
PRE_VERIFICATION_STATUSES = {
    STATUS_INVALID_FILE_TYPE,
    STATUS_DUPLICATE,
    STATUS_BLURRY,
    STATUS_WRONG_DOCUMENT,
    STATUS_FORGERY_DETECTED,
}

DOC_TYPE_LABELS = {
    "resume": "Resume",
    "cnic": "CNIC",
    "offer_letter": "Offer Letter",
    "degree": "Degree",
    "transcript": "Transcript",
    "internship_letter": "Internship Letter",
    "recommendation_letter": "Recommendation Letter",
    "certificate": "Certificate",
    "other": "Other",
}


def is_rejected(status: str) -> bool:
    return status in REJECTED_STATUSES


def doc_label(doc_type: str) -> str:
    return DOC_TYPE_LABELS.get(normalize_doc_type(doc_type), doc_type or "Unknown")


def rejection_verification(status: str, message: str, field: str = "validation", actions: list[str] | None = None) -> dict:
    """Build the verification record for a short-circuited upload."""
    return {
        "status": status,
        "confidence": 0.0,
        "issues": [{"field": field, "message": message, "severity": "critical"}],
        "recommended_actions": actions or ["Re-upload a valid document"],
        "engine": "rules",
        "reason": message,
    }


def check_wrong_document(expected_type: str, detected_type: str) -> dict | None:
    """Compare the declared document type against the classified one.

    Returns a rejection verification record when the classified document does
    not match what the user declared, else ``None`` (continue the pipeline).

    * expected set + detected known and different -> WRONG DOCUMENT TYPE
    * expected set + detected "other" (unclassifiable) -> FLAGGED (cannot be
      confirmed as the declared type, but not provably wrong either)
    * no expected type -> no check
    """
    expected = normalize_doc_type(expected_type)
    detected = normalize_doc_type(detected_type)

    if not expected or expected == "other":
        return None

    if detected == "other":
        return rejection_verification(
            STATUS_FLAGGED,
            f"Could not classify this document. It cannot be confirmed as {doc_label(expected)}.",
            field="classification",
            actions=["Upload a clearer copy of the document", "Verify the document type manually"],
        )

    if detected != expected:
        message = f"Expected document: {doc_label(expected)} · Detected: {doc_label(detected)}"
        return rejection_verification(
            STATUS_WRONG_DOCUMENT,
            message,
            field="doc_type",
            actions=[f"Upload the correct {doc_label(expected)} document"],
        )

    return None
