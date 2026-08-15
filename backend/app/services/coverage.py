"""Shared document-type normalization and required-document coverage logic.

Single source of truth for:
  * the canonical set of required document types
  * normalizing raw ``doc_type`` strings ("Offer Letter" -> "offer_letter")
  * detecting which required documents are actually present
  * computing overall + per-document coverage

Used both by the verification engine (when a submission is finalized) and by
API serialization (when a submission is read back), so the applicant
checklist, document coverage and key metrics always agree with the documents
actually stored — never with a stale aggregation snapshot.
"""
from __future__ import annotations

from app.config import settings

# Document statuses that mean "this upload never became a valid document".
# Such rows must NOT satisfy a required-document slot: the applicant did not
# actually provide that document. PASSED / FLAGGED / FAILED rows still count
# as present (the document exists — it is the verification that differs).
REJECTED_STATUSES = {
    "INVALID FILE TYPE",
    "DUPLICATE",
    "BLURRY",
    "WRONG DOCUMENT TYPE",
    "MISSING",
    "FORGERY DETECTED",
}

# Canonical type -> known aliases (any casing / separator spelling).
_DOC_TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    "resume": ("resume", "cv", "curriculum vitae", "curriculum_vitae"),
    "cnic": (
        "cnic",
        "id card",
        "identity card",
        "national id card",
        "national identity card",
        "nid card",
    ),
    "offer_letter": (
        "offer letter",
        "offer_letter",
        "letter of offer",
        "job offer",
        "employment offer",
        "offerletter",
        # An internship offer letter IS the internship portal's offer letter and
        # must satisfy the required offer_letter slot (it usually prints
        # "Internship offer", which the AI classifies as internship_letter).
        "internship offer",
        "internship letter",
        "internship_letter",
        "internship offer letter",
    ),
    "degree": ("degree", "degree certificate", "graduation certificate", "diploma"),
    "transcript": (
        "transcript",
        "transcript of records",
        "grade sheet",
        "gradesheet",
        "marksheet",
        "marks sheet",
    ),
    "recommendation_letter": (
        "recommendation letter",
        "recommendation_letter",
        "reference letter",
    ),
    "certificate": ("certificate", "participation certificate", "certification"),
}

_ALIAS_TO_CANONICAL: dict[str, str] = {
    alias: canonical
    for canonical, aliases in _DOC_TYPE_ALIASES.items()
    for alias in aliases
}


def normalize_doc_type(raw: str | None) -> str:
    """Map any user/LLM spelling to the canonical snake_case type.

    Handles case ("resume"/"Resume"/"RESUME") and separators
    ("offer_letter"/"Offer Letter"/"offer letter"). Unknown input -> "other".
    """
    if not raw:
        return "other"
    key = str(raw).strip().lower().replace("_", " ").replace("-", " ")
    return _ALIAS_TO_CANONICAL.get(key, "other")


def required_doc_types() -> list[str]:
    """Canonical list of document types required for 100% completeness."""
    return list(settings.COMPLETENESS_REQUIRED_DOCS)


def required_doc_set() -> set[str]:
    return set(settings.COMPLETENESS_REQUIRED_DOCS)


def present_doc_types(documents) -> set[str]:
    """Canonical doc types present among the documents (normalized, unique).

    ``documents`` items may be ORM rows or plain objects exposing ``doc_type``.
    Unknown/unclassified documents never satisfy a required type, and rejected
    uploads (invalid/duplicate/blurry/wrong-type) never count as
    present because they are not valid documents.
    """
    present: set[str] = set()
    for doc in documents:
        dt = getattr(doc, "doc_type", None) or ""
        if not dt:
            continue
        status = getattr(doc, "verification_status", None) or (doc.verification or {}).get("status", "")
        if status in REJECTED_STATUSES:
            continue
        canonical = normalize_doc_type(dt)
        if canonical != "other":
            present.add(canonical)
    return present


def compute_coverage(documents) -> dict:
    """Compute required-document coverage for one batch of documents.

    Returns a dict with:
      * ``coverage``        — present_required / total_required (0..1)
      * ``missing_documents`` — canonical types not present
      * ``required_documents`` — the canonical required set
      * ``documents``       — per-required-type presence stats
    """
    required = required_doc_types()
    present = present_doc_types(documents)
    per_doc = []
    for rtype in required:
        is_present = rtype in present
        per_doc.append(
            {
                "doc_type": rtype,
                "present": is_present,
                "present_count": 1 if is_present else 0,
                "total_batches": 1,
                "missing_count": 0 if is_present else 1,
                "rate": 1.0 if is_present else 0.0,
            }
        )
    missing = [rtype for rtype in required if rtype not in present]
    coverage = (len(required) - len(missing)) / len(required) if required else 0.0
    return {
        "coverage": round(coverage, 3),
        "missing_documents": missing,
        "required_documents": required,
        "documents": per_doc,
    }
