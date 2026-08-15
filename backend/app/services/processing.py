"""End-to-end document processing orchestrator.

The pipeline is *gated*: a document that fails an earlier stage is recorded
with the correct status and short-circuits — it is never OCR'd, classified or
verified as a valid document.

    UPLOAD ──> FILE TYPE ──> INTEGRITY ──> DUPLICATE ──> QUALITY/BLUR
           ──> FORGERY PRE-SCAN ──> OCR ──> CLASSIFY ──> WRONG-DOC ──> EXTRACT
           ──> FORGERY CONTENT/LLM ──> RULE VERIFY ──> INCONSISTENCIES (batch) ──> FINAL VERDICT
"""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.document import Document
from app.services import classification, duplicates, extraction, forgery, quality, verification
from app.services.ai.groq_client import groq_client
from app.services.ai.prompts import SUBMISSION_SUMMARY_SYSTEM, SUBMISSION_SUMMARY_USER
from app.services.coverage import REJECTED_STATUSES
from app.services.ocr import ocr_pipeline
from app.services.validation import check_wrong_document, rejection_verification

logger = get_logger("services.processing")

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}

BLURRY_MESSAGE = "The uploaded document image is too blurry for reliable verification. Please upload a clearer image."
DUPLICATE_MESSAGE = "This document has already been uploaded."


def rule_based_summary(submission, res: dict, inconsistencies: list[dict]) -> dict:
    """Complete deterministic submission summary produced without the LLM.

    Guarantees every report section (overall comment, highlights, concerns,
    recommended action, applicant name) is populated even when the Groq
    summary call fails or is unavailable.
    """
    highlights: list[str] = []
    concerns: list[str] = []

    names = {
        str(d.extracted["full_name"])
        for d in submission.documents
        if (d.verification or {}).get("status") not in REJECTED_STATUSES
        and d.extracted and d.extracted.get("full_name")
    }
    applicant_name = sorted(names)[0] if len(names) == 1 else ""
    if applicant_name:
        highlights.append(f"Applicant identified as {applicant_name}")

    cnic = next(
        (str(d.extracted["cnic"]) for d in submission.documents
         if d.extracted and d.extracted.get("cnic")), ""
    )
    if cnic:
        highlights.append(f"CNIC {cnic} extracted and internally consistent")
    if cnic and applicant_name:
        highlights.append("CNIC number matches the applicant's identity")

    for d in submission.documents:
        status = (d.verification or {}).get("status")
        extracted = d.extracted or {}
        label = (d.doc_type or "document").replace("_", " ")
        if status not in REJECTED_STATUSES:
            highlights.append(f"{label.title()} ({d.file_name}) verified with status {status}")
        for issue in (d.verification or {}).get("issues", []):
            if issue.get("severity") == "critical":
                concerns.append(f"{d.file_name}: {issue.get('message')}")

    for inc in inconsistencies:
        concerns.append(
            f"{inc.get('field_label', inc.get('field', 'Field'))} mismatch — "
            f"{inc.get('document_a')} has '{inc.get('value_a')}' but "
            f"{inc.get('document_b')} has '{inc.get('value_b')}'"
        )

    missing = res.get("missing_documents") or []
    for m in missing:
        concerns.append(f"{m.replace('_', ' ').title()} document is missing from the submission")

    if res.get("critical_documents"):
        concerns.append(f"{res['critical_documents']} document(s) failed verification")
    if res.get("flagged_documents"):
        concerns.append(f"{res['flagged_documents']} document(s) were flagged for manual review")
    if res.get("inconsistency_documents"):
        concerns.append("Cross-document inconsistencies were detected and require resolution")
    if res.get("forgery_documents"):
        concerns.append(
            f"{res['forgery_documents']} document(s) showed forgery / tampering indicators and were rejected"
        )

    status = res.get("status", "REVIEW")
    if status == "PASSED":
        overall = (
            f"All required documents were submitted and passed rule-based verification"
            + (f" for applicant {applicant_name}." if applicant_name else ".")
        )
        action = "ACCEPT"
    elif status == "FLAGGED":
        overall = (
            "The submission is incomplete or contains flagged documents requiring manual review."
            + (f" Applicant: {applicant_name}." if applicant_name else "")
        )
        action = "REVIEW"
    else:
        overall = (
            "The submission failed verification: critical documents are missing, rejected, "
            "or contain inconsistencies that must be resolved."
        )
        action = "REJECT"

    return {
        "overall_comment": overall,
        "highlights": highlights,
        "concerns": concerns,
        "recommended_action": action,
        "applicant_name": applicant_name,
        "engine": "rules",
    }


async def process_document(db: Session, doc: Document, expected_type: str = "") -> Document:
    """Run the gated pipeline on a single persisted Document row."""
    if expected_type:
        doc.expected_doc_type = expected_type
    path = Path(doc.stored_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Stored file missing: {doc.file_name}")

    # 1. DUPLICATE gate ---------------------------------------------------------
    # Runs before OCR so an already-uploaded document is never reprocessed.
    # Exact SHA-256 match catches identical PDFs; dHash catches re-encoded images.
    doc.duplicate = duplicates.detect_duplicate(db, doc)
    if doc.duplicate.get("is_duplicate"):
        reason = doc.duplicate.get("reason", DUPLICATE_MESSAGE)
        doc.verification = rejection_verification(
            "DUPLICATE", reason, field="duplicate",
            actions=["Remove the duplicate upload", f"Keep {doc.duplicate.get('matched_file') or 'the original'} only"],
        )
        db.commit()
        logger.info("REJECTED duplicate: %s (method=%s sim=%.2f)", doc.file_name, doc.duplicate.get("method"), doc.duplicate.get("similarity", 0))
        return doc

    # 2. QUALITY gate (blur) -----------------------------------------------------
    # Images are assessed directly; PDFs get a first-page render check.
    if doc.extension in IMAGE_EXTS:
        doc.quality = quality.assess_quality(path)
    else:
        doc.quality = quality.assess_pdf(path)
    if doc.quality.get("is_blurry"):
        doc.verification = rejection_verification(
            "BLURRY", BLURRY_MESSAGE, field="quality",
            actions=["Upload a clearer, sharper copy of the document"],
        )
        db.commit()
        logger.info("REJECTED blurry: %s (variance=%.2f)", doc.file_name, doc.quality.get("blur", 0))
        return doc

    # 3. FORGERY forensic pre-scan -------------------------------------------------
    # Image-only forensics run before OCR so a forged file is rejected before
    # any expensive OCR / classification work.
    doc.forgery = forgery.forensic_scan(path)
    db.commit()
    if doc.forgery.get("level") == "RED":
        doc.verification = forgery.forgery_rejection(doc.forgery)
        db.commit()
        logger.info("REJECTED forgery (forensic pre-scan): %s", doc.file_name)
        return doc

    # 4. OCR ----------------------------------------------------------------------
    ocr_result = await ocr_pipeline.extract(path, doc.extension)
    doc.raw_text = ocr_result.text
    doc.ocr_provider = ocr_result.provider
    doc.ocr_confidence = ocr_result.confidence
    doc.language = ocr_result.language
    doc.page_count = len(ocr_result.pages) or 1
    db.commit()

    # 5. Classification -----------------------------------------------------------
    cls = await classification.classify(doc.raw_text)
    doc.doc_type = cls["doc_type"]
    doc.classification_confidence = cls["confidence"]
    db.commit()

    # 6. WRONG DOCUMENT gate ------------------------------------------------------
    # Compare what the user declared against what the document actually is.
    wrong = check_wrong_document(doc.expected_doc_type or "", doc.doc_type)
    if wrong:
        doc.verification = wrong
        db.commit()
        logger.info(
            "REJECTED wrong document: %s (expected=%s detected=%s)",
            doc.file_name, doc.expected_doc_type or "-", doc.doc_type,
        )
        return doc

    # 7. Information extraction -----------------------------------------------------
    doc.extracted = await extraction.extract(doc.raw_text, doc.doc_type)
    db.commit()

    # 7b. FORGERY content + LLM analysis ----------------------------------------------
    # Merge content-level checks (CNIC format, impossible dates, fake markers)
    # with the earlier forensic pre-scan, then let the LLM (if available) review.
    doc.forgery = forgery.combine_signals(
        doc.forgery,
        forgery.content_signal(doc.doc_type, doc.extracted or {}, doc.raw_text or ""),
    )
    db.commit()
    if doc.forgery.get("level") == "RED":
        doc.verification = forgery.forgery_rejection(doc.forgery)
        db.commit()
        logger.info("REJECTED forgery (content analysis): %s", doc.file_name)
        return doc

    llm = await forgery.llm_analysis(
        doc.doc_type, doc.extracted or {}, doc.raw_text or "", doc.forgery.get("signals", [])
    )
    if llm:
        doc.forgery = forgery.apply_llm(doc.forgery, llm)
        db.commit()
        if doc.forgery.get("level") == "RED":
            doc.verification = forgery.forgery_rejection(doc.forgery)
            db.commit()
            logger.info("REJECTED forgery (LLM analysis): %s", doc.file_name)
            return doc

    # 8. Rule-based verification --------------------------------------------------------
    doc.verification = verification.verify_document_rules(doc)
    db.commit()

    # 9. AI decision support (augments, never overrides) --------------------------------
    ai = await verification.ai_decision_support(doc)
    if ai.get("augmented"):
        analysis = ai.get("analysis") or {}
        if isinstance(analysis, dict):
            for key in ("status", "confidence", "issues", "recommended_actions"):
                if key in analysis:
                    doc.verification[key] = analysis[key]
            doc.verification["engine"] = "rules+llm"
    db.commit()

    logger.info(
        "Processed %s → %s | status=%s conf=%.2f",
        doc.file_name, doc.doc_type, doc.verification.get("status"), doc.verification.get("confidence", 0),
    )
    return doc


async def finalize_submission(db: Session, submission) -> None:
    """Aggregate results, run batch-level inconsistency checks, generate report."""
    # Batch-level gate: cross-document identity consistency.
    inconsistencies = verification.detect_inconsistencies(submission.documents)
    if inconsistencies:
        verification.apply_inconsistencies(submission.documents, inconsistencies)
        db.commit()
        logger.info(
            "Submission #%s: %d inconsistency(ies) detected",
            submission.id, len(inconsistencies),
        )

    res = verification.compute_submission_verification(submission.documents)
    submission.status = res["status"]
    submission.completeness_score = res["completeness_score"]
    submission.overall_confidence = res["overall_confidence"]
    submission.missing_documents = res["missing_documents"]
    submission.duplicate_documents = res["duplicate_documents"]
    submission.summary = {**res, "inconsistencies": inconsistencies}
    db.commit()

    summary_ok = False
    if groq_client.available:
        try:
            summary_resp = await groq_client.complete_json(
                SUBMISSION_SUMMARY_SYSTEM,
                SUBMISSION_SUMMARY_USER.format(summary=res),
                max_tokens=700,
            )
            submission.summary = {**submission.summary, **groq_client.parse_json(summary_resp["content"])}
            summary_ok = True
            db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Submission summary LLM failed: %s", exc)

    if not summary_ok:
        # Guarantee a complete summary even without the LLM.
        submission.summary = {
            **submission.summary,
            **rule_based_summary(submission, res, inconsistencies),
        }
        db.commit()

    from app.services.reporting import build_report_json, generate_report

    _, url = generate_report(submission)
    submission.report_data = build_report_json(submission)
    db.commit()
    logger.info("Submission #%s finalized: %s", submission.id, submission.status)
