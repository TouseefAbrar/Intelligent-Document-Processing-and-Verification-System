from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.core.logging import get_logger
from app.database import get_db
from app.models.document import Document, Submission
from app.schemas.document import SubmissionDetail, SubmissionResponse
from app.services.processing import finalize_submission, process_document
from app.services.validation import rejection_verification
from app.services.verification import compute_submission_verification
from app.utils.files import (
    remove_file,
    sha256_bytes,
    store_upload,
    validate_file_bytes,
    validate_file_integrity,
)

router = APIRouter(prefix="/submissions", tags=["submissions"])

logger = get_logger("api.submissions")


def _doc_summary(doc: Document) -> dict:
    return {
        "id": doc.id,
        "file_name": doc.file_name,
        "doc_type": doc.doc_type,
        "expected_doc_type": getattr(doc, "expected_doc_type", "") or "",
        "classification_confidence": doc.classification_confidence,
        "ocr_confidence": doc.ocr_confidence,
        "verification_status": doc.verification.get("status", "PENDING"),
        "language": doc.language,
        "file_size": doc.file_size,
    }


def _doc_detail(doc: Document) -> dict:
    return {
        **_doc_summary(doc),
        "extracted": doc.extracted or {},
        "quality": doc.quality or {},
        "duplicate": doc.duplicate or {},
        "verification": doc.verification or {},
        "forgery": getattr(doc, "forgery", None) or {},
        "ocr_provider": doc.ocr_provider,
        "raw_text_preview": (doc.raw_text or "")[:400],
        "created_at": doc.created_at.isoformat(),
    }


def _submission_out(sub: Submission, include_details: bool = False) -> dict:
    # Derive presence-based fields from the documents actually stored so the
    # serialized submission always agrees with the applicant checklist and
    # document-coverage UI — even when the stored snapshot is stale.
    agg = compute_submission_verification(sub.documents)
    out = {
        "id": sub.id,
        "applicant_ref": sub.applicant_ref,
        "status": agg["status"],
        "completeness_score": agg["completeness_score"],
        "overall_confidence": agg["overall_confidence"],
        "missing_documents": agg["missing_documents"],
        "duplicate_documents": sub.duplicate_documents or [],
        "summary": sub.summary or {},
        "report_url": f"/api/v1/submissions/{sub.id}/report",
        "documents": [_doc_summary(d) for d in sub.documents],
        "created_at": sub.created_at.isoformat(),
    }
    if include_details:
        out["documents"] = [_doc_detail(d) for d in sub.documents]
    return out


def _rejected_document(file: UploadFile, raw: bytes, message: str, expected_type: str) -> Document:
    """Create a Document row for an upload that failed file validation.

    The file is NOT stored and it never enters the processing pipeline.
    """
    return Document(
        file_name=file.filename or "unnamed",
        stored_path="",
        file_size=len(raw),
        mime_type=file.content_type or "",
        extension=Path(file.filename or "").suffix.lower(),
        sha256=sha256_bytes(raw) if raw else "",
        expected_doc_type=expected_type or "",
        verification=rejection_verification(
            "INVALID FILE TYPE",
            message,
            field="file_type",
            actions=["Upload a supported file (PDF, JPG, JPEG or PNG)"],
        ),
    )


@router.post("/upload", response_model=SubmissionDetail, status_code=201,
             summary="Upload a batch of documents and verify them as one submission")
async def upload_submission(
    files: list[UploadFile] = File(...),
    expected_types: list[str] = Form(default=[]),
    applicant_ref: str = Form(default=""),
    db: Session = Depends(get_db),
) -> SubmissionDetail:
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    submission = Submission(
        applicant_ref=applicant_ref,
        status="PROCESSING",
        completeness_score=0.0,
        overall_confidence=0.0,
        missing_documents=[],
        duplicate_documents=[],
        summary={},
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    created_docs: list[Document] = []
    for i, file in enumerate(files):
        expected = (expected_types[i] if i < len(expected_types) else "") or ""

        # ---- Stage: FILE TYPE validation (extension + magic bytes + MIME) ----
        raw = await file.read()
        result = validate_file_bytes(raw, file.filename, file.content_type)
        if not result["ok"]:
            doc = _rejected_document(file, raw, result["message"], expected)
            doc.submission_id = submission.id
            db.add(doc)
            db.commit()
            db.refresh(doc)
            created_docs.append(doc)
            logger.info("Rejected %s: %s", file.filename, result["message"])
            continue

        # ---- Stage: FILE INTEGRITY validation (actually decodable) ----
        path = store_upload(raw, result["extension"])
        integrity = validate_file_integrity(path, result["extension"])
        if not integrity["ok"]:
            path.unlink(missing_ok=True)
            doc = _rejected_document(file, raw, integrity["message"], expected)
            doc.submission_id = submission.id
            db.add(doc)
            db.commit()
            db.refresh(doc)
            created_docs.append(doc)
            continue

        doc = Document(
            file_name=file.filename or path.name,
            stored_path=str(path),
            file_size=path.stat().st_size,
            mime_type=file.content_type or "",
            extension=result["extension"],
            sha256=sha256_bytes(raw),
            expected_doc_type=expected,
            submission_id=submission.id,
            verification={"status": "PROCESSING", "issues": [], "recommended_actions": []},
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        created_docs.append(doc)

    failures: list[str] = []
    for doc in created_docs:
        # Rejected uploads were already short-circuited — never process them.
        if doc.verification.get("status") in ("INVALID FILE TYPE",):
            continue
        try:
            await process_document(db, doc, expected_type=doc.expected_doc_type)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Processing failed for %s", doc.file_name)
            doc.verification = {
                "status": "FAILED",
                "issues": [{"field": "pipeline", "message": f"Processing error: {exc}", "severity": "critical"}],
                "recommended_actions": ["Re-upload the document"],
            }
            db.commit()
            failures.append(doc.file_name)

    await finalize_submission(db, submission)
    db.refresh(submission)
    return SubmissionDetail(**_submission_out(submission, include_details=True))


@router.get("", response_model=list[SubmissionResponse], summary="List all submissions")
def list_submissions(db: Session = Depends(get_db)) -> list[SubmissionResponse]:
    subs = db.query(Submission).order_by(Submission.created_at.desc()).limit(100).all()
    return [SubmissionResponse(**_submission_out(s, include_details=False)) for s in subs]


@router.get("/export.csv", summary="Export all submissions as a CSV report")
def export_submissions(db: Session = Depends(get_db)) -> FileResponse:
    import csv
    import io

    subs = db.query(Submission).order_by(Submission.created_at.desc()).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "submission_id", "applicant_ref", "status", "completeness_score",
        "overall_confidence", "documents_checked", "missing_documents",
        "duplicate_documents", "forgery_documents", "recommended_action", "created_at",
    ])
    for s in subs:
        writer.writerow([
            s.id,
            s.applicant_ref,
            s.status,
            s.completeness_score,
            s.overall_confidence,
            len(s.documents),
            "|".join(s.missing_documents or []),
            "|".join(s.duplicate_documents or []),
            len([d for d in s.documents if d.verification.get("status") == "FORGERY DETECTED"]),
            (s.summary or {}).get("recommended_action", ""),
            s.created_at.isoformat(),
        ])
    data = buf.getvalue()
    path = settings.data_dir / "export_submissions.csv"
    path.write_text(data, encoding="utf-8-sig")
    return FileResponse(path, media_type="text/csv", filename="eef_submissions.csv")


@router.get("/{sub_id}", response_model=SubmissionDetail, summary="Get submission with document details")
def get_submission(sub_id: int, db: Session = Depends(get_db)) -> SubmissionDetail:
    sub = db.get(Submission, sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    return SubmissionDetail(**_submission_out(sub, include_details=True))


@router.get("/{sub_id}/report", summary="Download the verification report (html or pdf)")
def download_report(sub_id: int, format: str = "html", db: Session = Depends(get_db)) -> FileResponse:
    sub = db.get(Submission, sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")

    fmt = format.lower()
    if fmt == "pdf":
        from app.services.reporting import generate_report

        pdf_path = settings.report_dir / f"submission_{sub.id}.pdf"
        generate_report(sub, with_pdf=True)
        if not pdf_path.exists():
            raise HTTPException(status_code=501, detail="PDF generation requires weasyprint")
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=f"eef_report_{sub.id}.pdf",
            headers={"Cache-Control": "no-store"},
        )

    html_path = settings.report_dir / f"submission_{sub.id}.html"
    generate_report(sub)
    return FileResponse(
        html_path,
        media_type="text/html",
        filename=f"eef_report_{sub.id}.html",
        headers={"Cache-Control": "no-store"},
    )


@router.delete("/{sub_id}", status_code=204, summary="Delete a submission and its files")
def delete_submission(sub_id: int, db: Session = Depends(get_db)) -> None:
    sub = db.get(Submission, sub_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    for doc in sub.documents:
        if doc.stored_path:
            remove_file(Path(doc.stored_path))
    db.delete(sub)
    db.commit()
