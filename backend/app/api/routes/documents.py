from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.database import get_db
from app.models.document import Document
from app.schemas.document import DocumentDetail
from app.services.processing import process_document
from app.utils.files import remove_file, save_upload, sha256_of

router = APIRouter(prefix="/documents", tags=["documents"])

logger = get_logger("api.documents")


def _to_detail(doc: Document) -> DocumentDetail:
    return DocumentDetail(
        id=doc.id,
        file_name=doc.file_name,
        doc_type=doc.doc_type,
        expected_doc_type=doc.expected_doc_type or "",
        classification_confidence=doc.classification_confidence,
        ocr_confidence=doc.ocr_confidence,
        verification_status=doc.verification.get("status", "PENDING"),
        language=doc.language,
        file_size=doc.file_size,
        extracted=doc.extracted or {},
        quality=doc.quality or {},
        duplicate=doc.duplicate or {},
        verification=doc.verification or {},
        forgery=doc.forgery or {},
        ocr_provider=doc.ocr_provider,
        raw_text_preview=(doc.raw_text or "")[:400],
        created_at=doc.created_at,
    )


@router.post(
    "/upload",
    response_model=DocumentDetail,
    status_code=201,
    summary="Upload + fully process a single document",
)
async def upload_document(
    file: UploadFile = File(...),
    expected_type: str = Form(default=""),
    db: Session = Depends(get_db),
) -> DocumentDetail:
    path, ext = await save_upload(file)
    doc = Document(
        file_name=file.filename or path.name,
        stored_path=str(path),
        file_size=path.stat().st_size,
        mime_type=file.content_type or "",
        extension=ext,
        sha256=sha256_of(path),
        expected_doc_type=expected_type or "",
        verification={"status": "PROCESSING", "issues": [], "recommended_actions": []},
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    try:
        doc = await process_document(db, doc, expected_type=doc.expected_doc_type)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Processing failed for %s", doc.file_name)
        doc.verification = {
            "status": "FAILED",
            "issues": [{"field": "pipeline", "message": f"Processing error: {exc}", "severity": "critical"}],
            "recommended_actions": ["Re-upload the document"],
        }
        db.commit()
        raise HTTPException(status_code=422, detail=f"Document processing failed: {exc}")

    return _to_detail(doc)


@router.delete("/{doc_id}", status_code=204, summary="Delete a document and its stored file")
def delete_document(doc_id: int, db: Session = Depends(get_db)) -> None:
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    remove_file(Path(doc.stored_path))
    db.delete(doc)
    db.commit()


@router.get("/{doc_id}", response_model=DocumentDetail, summary="Fetch processed document detail")
def get_document(doc_id: int, db: Session = Depends(get_db)) -> DocumentDetail:
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return _to_detail(doc)
