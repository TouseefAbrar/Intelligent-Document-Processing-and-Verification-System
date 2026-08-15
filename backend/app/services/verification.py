"""Rule-based validation + AI decision-support for document verification.

Combines every signal produced earlier (OCR confidence, quality metrics,
duplicate detection, extraction completeness) into:
  * per-document verification verdicts and issues
  * cross-document inconsistency detection
  * submission completeness scoring
  * recommended actions for human reviewers
"""
from __future__ import annotations

import re

from app.config import settings
from app.core.logging import get_logger
from app.services.ai.groq_client import groq_client
from app.services.ai.prompts import VERIFICATION_ANALYSIS_SYSTEM, VERIFICATION_ANALYSIS_USER
from app.services.coverage import compute_coverage, REJECTED_STATUSES
from app.services.validation import (
    STATUS_INCONSISTENCY,
    STATUS_PASSED,
    STATUS_FLAGGED,
    STATUS_FAILED,
    STATUS_FORGERY_DETECTED,
)

logger = get_logger("services.verification")

TYPE_REQUIRED_FIELDS: dict[str, list[str]] = {
    "resume": ["full_name", "email", "phone", "skills"],
    "cnic": ["cnic", "full_name"],
    "offer_letter": ["full_name", "issuer", "position"],
    "degree": ["full_name", "degree", "university"],
    "transcript": ["university", "cgpa"],
    "internship_letter": ["full_name", "issuer"],
    "recommendation_letter": ["full_name", "issuer"],
    "certificate": ["full_name", "issuer", "issue_date"],
}

# Fields that should agree across documents, and their human labels.
INCONSISTENT_FIELDS: list[tuple[str, str]] = [
    ("full_name", "Name"),
    ("cnic", "CNIC"),
    ("date_of_birth", "Date of birth"),
    ("father_name", "Father's name"),
    ("university", "Institution"),
    ("degree", "Degree/Program"),
]

# Identity fields are treated as critical when they conflict.
_IDENTITY_FIELDS = {"full_name", "cnic", "date_of_birth", "father_name"}


def _missing_fields(doc_type: str, extracted: dict) -> list[str]:
    required = TYPE_REQUIRED_FIELDS.get(doc_type, [])
    return [f for f in required if not extracted.get(f)]


def verify_document_rules(document) -> dict:
    """Pure rule-based verification of a single Document row.

    Only reached by documents that passed every pre-verification gate, so
    invalid/duplicate/blurry/wrong-type uploads never land here.
    """
    issues: list[dict] = []
    status = STATUS_PASSED
    confidence = document.ocr_confidence

    # 1. OCR quality
    if not document.raw_text.strip():
        issues.append({"field": "ocr", "message": "No text could be extracted", "severity": "critical"})
        status = STATUS_FAILED
        confidence -= 0.4
    else:
        if document.ocr_confidence < 0.5:
            issues.append({"field": "ocr", "message": f"Low OCR confidence ({document.ocr_confidence:.0%})", "severity": "warning"})
        # 2. Image quality signals
        q = document.quality or {}
        for issue in q.get("issues", []):
            issues.append({"field": "quality", "message": issue, "severity": "warning"})
        # 3. Duplicate
        d = document.duplicate or {}
        if d.get("is_duplicate"):
            issues.append({
                "field": "duplicate",
                "message": f"Possible duplicate upload (similarity {d.get('similarity', 0):.0%})",
                "severity": "critical",
            })
            status = STATUS_FAILED
            confidence -= 0.3
        # 3b. Forgery / fake-document signals (RED is rejected earlier in the pipeline)
        f = getattr(document, "forgery", None) or {}
        if f.get("level") == "YELLOW":
            issues.append({
                "field": "forgery",
                "message": f"Possible forged or edited document — {f.get('note') or 'suspicious forensic signals'}",
                "severity": "warning",
            })
            if status == STATUS_PASSED:
                status = STATUS_FLAGGED
            confidence -= 0.15
        # 4. Field completeness per document type
        missing = _missing_fields(document.doc_type, document.extracted or {})
        for field in missing:
            issues.append({"field": field, "message": f"Missing/invalid: {field}", "severity": "warning"})
        if missing and status == STATUS_PASSED:
            status = STATUS_FLAGGED
            confidence -= 0.1 * len(missing)
        # 5. Type-specific sanity checks
        extracted = document.extracted or {}
        if document.doc_type == "cnic":
            if not extracted.get("cnic"):
                issues.append({"field": "cnic", "message": "CNIC number not found on identity card", "severity": "critical"})
                status = STATUS_FAILED
        if document.doc_type == "transcript" and extracted.get("cgpa") is None:
            issues.append({"field": "cgpa", "message": "CGPA not detected on transcript", "severity": "info"})
        if extracted.get("expiry_date") and not _is_valid_expiry(extracted["expiry_date"]):
            issues.append({"field": "expiry_date", "message": "Document appears to be expired", "severity": "warning"})

    confidence = max(0.0, min(1.0, confidence))
    recommended = _recommended_actions(status, issues)

    return {
        "status": status,
        "confidence": round(confidence, 3),
        "issues": issues,
        "recommended_actions": recommended,
        "engine": "rules",
    }


def _is_valid_expiry(expiry: str) -> bool:
    from datetime import date

    try:
        return date.fromisoformat(expiry) >= date.today()
    except (ValueError, TypeError):
        return True  # unknown format → don't fail on it


def _recommended_actions(status: str, issues: list[dict]) -> list[str]:
    actions: list[str] = []
    severities = {i["severity"] for i in issues}
    if "critical" in severities:
        actions.append("Request the applicant to re-upload a clear copy")
    if "warning" in severities:
        actions.append("Manual review recommended before approval")
    if status == STATUS_PASSED:
        actions.append("No action required — document verified automatically")
    if not actions:
        actions.append("Manual review recommended")
    return actions


# --- Cross-document inconsistency detection ----------------------------------

def _normalize_value(field: str, value) -> str:
    """Normalize a field value for identity comparison.

    CNIC / dates / father's-name strip all non-alphanumeric characters so
    "35202-1234567-1" equals "35202 1234567 1". Other fields collapse
    whitespace and case.
    """
    text = str(value or "").strip()
    if field in ("cnic", "date_of_birth", "father_name"):
        return re.sub(r"[^a-z0-9]", "", text.lower())
    return re.sub(r"\s+", " ", text).lower()


def detect_inconsistencies(documents) -> list[dict]:
    """Compare identity fields across documents in one submission.

    Only fields that are expected on the involved document types are compared
    (see ``INCONSISTENT_FIELDS``), and only when both sides actually contain a
    value — a missing field never counts as an inconsistency.
    """
    records: list[dict] = []
    for field, label in INCONSISTENT_FIELDS:
        # Collect every document that has a value for this field.
        entries: list[tuple[object, str, str]] = []
        for doc in documents:
            status = getattr(doc, "verification_status", None) or (doc.verification or {}).get("status", "")
            if status in REJECTED_STATUSES:
                continue  # rejected uploads never took part in extraction
            extracted = getattr(doc, "extracted", None) or {}
            value = extracted.get(field)
            normalized = _normalize_value(field, value)
            if not normalized:
                continue
            entries.append((doc, normalized, str(value)))

        if len(entries) < 2:
            continue

        groups: dict[str, list[tuple[object, str]]] = {}
        for doc, normalized, raw in entries:
            groups.setdefault(normalized, []).append((doc, raw))

        if len(groups) < 2:
            continue

        keys = list(groups.keys())
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                doc_a, raw_a = groups[keys[i]][0]
                doc_b, raw_b = groups[keys[j]][0]
                records.append({
                    "field": field,
                    "field_label": label,
                    "document_a": doc_a.file_name,
                    "document_a_id": getattr(doc_a, "id", None),
                    "value_a": raw_a,
                    "document_b": doc_b.file_name,
                    "document_b_id": getattr(doc_b, "id", None),
                    "value_b": raw_b,
                    "expected": f"Matching {label.lower()} information across documents",
                    "actual": "Different values",
                    "severity": "critical" if field in _IDENTITY_FIELDS else "warning",
                })
    return records


def apply_inconsistencies(documents, inconsistencies: list[dict]) -> None:
    """Mark the documents involved in inconsistencies.

    Every involved document receives the INCONSISTENCY DETECTED status plus a
    clear issue describing the conflicting fields.
    """
    involved_ids: set[int] = set()
    for inc in inconsistencies:
        for key in ("document_a_id", "document_b_id"):
            if inc.get(key) is not None:
                involved_ids.add(int(inc[key]))

    for doc in documents:
        if doc.id not in involved_ids:
            continue
        issues = doc.verification.setdefault("issues", [])
        for inc in inconsistencies:
            if int(inc["document_a_id"]) == doc.id or int(inc["document_b_id"]) == doc.id:
                issues.append({
                    "field": inc["field"],
                    "message": (
                        f"{inc['field_label']} mismatch — {inc['document_a']} "
                        f"has '{inc['value_a']}' but {inc['document_b']} has '{inc['value_b']}'"
                    ),
                    "severity": inc["severity"],
                })
        doc.verification["status"] = STATUS_INCONSISTENCY


async def ai_decision_support(document) -> dict:
    """LLM-based analysis that augments (never replaces) the rule layer."""
    if not groq_client.available:
        return {"engine": "rules", "augmented": False}
    try:
        resp = await groq_client.complete_json(
            VERIFICATION_ANALYSIS_SYSTEM,
            VERIFICATION_ANALYSIS_USER.format(
                doc_type=document.doc_type,
                extracted=str(document.extracted or {}),
                quality=str(document.quality or {}),
                text=(document.raw_text or "")[:600],
            ),
            max_tokens=700,
        )
        return {"engine": "groq-llm", "augmented": True, "analysis": resp.get("content", "")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI decision support skipped: %s", exc)
        return {"engine": "rules", "augmented": False}


def compute_submission_verification(documents) -> dict:
    """Aggregate per-document results into a submission-level verdict.

    Document existence is determined via the shared coverage service so the
    verdict is computed from the documents actually stored (normalized types),
    never from a stale snapshot. FLAGGED / FAILED documents still count as
    present; rejected uploads (invalid, duplicate, blurry, wrong type) never
    satisfy a required slot.
    """
    coverage = compute_coverage(documents)
    missing = coverage["missing_documents"]
    completeness = coverage["coverage"]

    # Confidence is averaged over documents that actually reached verification.
    verified = [d for d in documents if (d.verification or {}).get("status") not in REJECTED_STATUSES]
    overall_conf = (
        sum(d.verification.get("confidence", 0.0) for d in verified) / len(verified)
        if verified else 0.0
    )
    duplicates = [
        d.file_name for d in documents if (d.duplicate or {}).get("is_duplicate")
    ]
    critical = sum(
        1 for d in documents
        if d.verification.get("status") == "FAILED"
    )
    flagged = sum(
        1 for d in documents
        if d.verification.get("status") == "FLAGGED"
    )
    inconsistencies = sum(
        1 for d in documents
        if d.verification.get("status") == STATUS_INCONSISTENCY
    )
    invalid = sum(
        1 for d in documents
        if d.verification.get("status") == "INVALID FILE TYPE"
    )
    wrong_type = sum(
        1 for d in documents
        if d.verification.get("status") == "WRONG DOCUMENT TYPE"
    )
    forgery_docs = sum(
        1 for d in documents
        if d.verification.get("status") == STATUS_FORGERY_DETECTED
    )

    if inconsistencies:
        status = STATUS_INCONSISTENCY
    elif forgery_docs or missing or critical:
        status = "FAILED"
    elif flagged or completeness < 1.0:
        status = STATUS_FLAGGED
    else:
        status = STATUS_PASSED

    return {
        "status": status,
        "completeness_score": round(completeness, 3),
        "overall_confidence": round(overall_conf, 3),
        "missing_documents": missing,
        "duplicate_documents": duplicates,
        "documents_checked": len(documents),
        "critical_documents": critical,
        "flagged_documents": flagged,
        "inconsistency_documents": inconsistencies,
        "invalid_documents": invalid,
        "wrong_type_documents": wrong_type,
        "forgery_documents": forgery_docs,
    }
