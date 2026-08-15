"""Tests for the pre-verification validation gates.

Covers the critical behaviour that was previously broken:
  * invalid file types are rejected on content, not just extension
  * exact (SHA-256) duplicate uploads are caught before OCR
  * blurry images are rejected by the quality gate before OCR
  * wrong-document (expected vs detected) detection
  * cross-document inconsistency detection
  * rejected uploads never satisfy required-document coverage
  * the pipeline short-circuits (OCR is never invoked on rejected uploads)
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.utils import files as file_utils


# --- File type validation -----------------------------------------------------

def test_validate_rejects_unsupported_extension():
    res = file_utils.validate_file_bytes(b"%PDF-1.4", "note.txt", None)
    assert res["ok"] is False
    assert "Unsupported file type" in res["message"]


def test_validate_rejects_renamed_text_file_as_pdf():
    # .pdf extension but the content is plain text (no magic bytes match).
    res = file_utils.validate_file_bytes(b"hello world, this is not a pdf at all", "fake.pdf", "application/pdf")
    assert res["ok"] is False
    assert "Unsupported file type" in res["message"]


def test_validate_rejects_extension_content_mismatch():
    res = file_utils.validate_file_bytes(b"\x89PNG\r\n\x1a\n...", "doc.pdf", "image/png")
    assert res["ok"] is False
    assert "does not match its extension" in res["message"]


def test_validate_accepts_real_pdf_and_png():
    assert file_utils.validate_file_bytes(b"%PDF-1.4 xref", "doc.pdf", "application/pdf")["ok"] is True
    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0d"
    assert file_utils.validate_file_bytes(png, "img.png", "image/png")["ok"] is True


def test_validate_jpeg_jpg_aliasing_allowed():
    res = file_utils.validate_file_bytes(b"\xff\xd8\xff\xe0", "photo.jpeg", "image/jpeg")
    assert res["ok"] is True
    assert res["extension"] == ".jpg"


# --- Wrong document detection -------------------------------------------------

from app.services.validation import check_wrong_document  # noqa: E402


def test_wrong_document_cnic_vs_resume():
    res = check_wrong_document("CNIC", "resume")
    assert res is not None
    assert res["status"] == "WRONG DOCUMENT TYPE"
    assert "Expected document: CNIC" in res["issues"][0]["message"]
    assert "Detected: Resume" in res["issues"][0]["message"]


def test_wrong_document_match_passes():
    assert check_wrong_document("CNIC", "cnic") is None
    assert check_wrong_document("Offer Letter", "offer_letter") is None


def test_wrong_document_no_expected_no_check():
    assert check_wrong_document("", "resume") is None
    assert check_wrong_document("auto", "resume") is None


def test_unclassifiable_document_is_not_passed():
    res = check_wrong_document("degree", "other")
    assert res is not None
    assert res["status"] == "FLAGGED"
    assert "cannot be confirmed" in res["issues"][0]["message"]


# --- Duplicate detection (SHA-256 exact) --------------------------------------

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models.document import Document, Submission  # noqa: E402
from app.services.duplicates import detect_duplicate  # noqa: E402


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _stored_doc(**kw):
    defaults = {
        "file_name": "doc.pdf",
        "stored_path": "",
        "file_size": 10,
        "mime_type": "application/pdf",
        "extension": ".pdf",
        "sha256": "abc123",
        "verification": {"status": "PROCESSING", "issues": []},
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(kw)
    return Document(**defaults)


def test_sha256_exact_duplicate_detected(db_session):
    sub = Submission(applicant_ref="A1")
    db_session.add(sub)
    db_session.commit()
    first = _stored_doc(file_name="offer.pdf", sha256="deadbeef", submission_id=sub.id)
    second = _stored_doc(file_name="offer_copy.pdf", sha256="deadbeef", submission_id=sub.id)
    # Simulate the real flow: the first document finished processing (PASSED)
    # before the second copy is checked for duplicates.
    first.verification = {"status": "PASSED", "issues": []}
    db_session.add_all([first, second])
    db_session.commit()

    res = detect_duplicate(db_session, second)
    assert res["is_duplicate"] is True
    assert res["method"] == "sha256"
    assert res["similarity"] == 1.0
    assert res["matched_file"] == "offer.pdf"


def test_distinct_files_are_not_duplicates(db_session):
    sub = Submission(applicant_ref="A1")
    db_session.add(sub)
    db_session.commit()
    first = _stored_doc(file_name="resume.pdf", sha256="aaaa", submission_id=sub.id)
    second = _stored_doc(file_name="cnic.pdf", sha256="bbbb", submission_id=sub.id)
    first.verification = {"status": "PASSED", "issues": []}
    db_session.add_all([first, second])
    db_session.commit()

    res = detect_duplicate(db_session, second)
    assert res["is_duplicate"] is False


def test_unprocessed_sibling_is_not_a_duplicate_source(db_session):
    # Both batch siblings exist in the DB with identical bytes but NEITHER has
    # been processed yet — the first one must not be flagged a duplicate.
    sub = Submission(applicant_ref="A1")
    db_session.add(sub)
    db_session.commit()
    first = _stored_doc(file_name="offer.pdf", sha256="deadbeef", submission_id=sub.id)
    second = _stored_doc(file_name="offer_copy.pdf", sha256="deadbeef", submission_id=sub.id)
    db_session.add_all([first, second])
    db_session.commit()

    res = detect_duplicate(db_session, first)
    assert res["is_duplicate"] is False


# --- Quality gates (blurry) ---------------------------------------------------

from PIL import Image  # noqa: E402

import numpy as np  # noqa: E402

from app.services import quality  # noqa: E402


def _write_synthetic_image(tmp_path, name, size, blur_sigma, background=215):
    import cv2

    w, h = size
    img = np.full((h, w), background, dtype=np.uint8)
    step = max(6, w // 10)
    for x in range(0, w, step):
        img[:, x : x + 3] = 40
    for y in range(0, h, step):
        img[y : y + 3, :] = 40
    if blur_sigma > 0:
        img = cv2.GaussianBlur(img, (0, 0), blur_sigma)
    path = tmp_path / name
    Image.fromarray(img).save(path)
    return path


def test_quality_flags_blurry_image(tmp_path):
    path = _write_synthetic_image(tmp_path, "blur.png", (1600, 1200), blur_sigma=20)
    res = quality.assess_quality(path)
    assert res["is_blurry"] is True
    assert res["blur"] < 100


def test_quality_passes_sharp_highres_image(tmp_path):
    path = _write_synthetic_image(tmp_path, "sharp.png", (1800, 1400), blur_sigma=0)
    res = quality.assess_quality(path)
    assert res["is_blurry"] is False
    assert res["blur"] >= 100
    assert res["quality_score"] > 0.5


# --- Pipeline short-circuit ------------------------------------------------------

from app.services.ocr.base import OCRResult  # noqa: E402


class _FakeOCR:
    async def extract(self, path, extension, **kw):
        raise AssertionError("OCR must not run on a rejected upload")


async def _run_pipeline(db_session, doc, monkeypatch, fake_ocr=None):
    import app.services.processing as processing

    if fake_ocr is None:
        fake_ocr = _FakeOCR()
    monkeypatch.setattr(processing.ocr_pipeline, "extract", fake_ocr.extract)
    return await processing.process_document(db_session, doc, expected_type="")


def test_duplicate_short_circuits_before_ocr(db_session, tmp_path, monkeypatch):
    import asyncio

    sub = Submission(applicant_ref="A1")
    db_session.add(sub)
    db_session.commit()
    first = _stored_doc(file_name="offer.pdf", sha256="deadbeef", submission_id=sub.id)
    second = _stored_doc(file_name="copy.pdf", sha256="deadbeef", submission_id=sub.id)
    first.verification = {"status": "PASSED", "issues": []}
    db_session.add_all([first, second])
    db_session.commit()

    doc = asyncio.get_event_loop().run_until_complete(_run_pipeline(db_session, second, monkeypatch))
    assert doc.verification["status"] == "DUPLICATE"
    assert not doc.raw_text


def test_blurry_short_circuits_before_ocr(db_session, tmp_path, monkeypatch):
    import asyncio

    path = _write_synthetic_image(tmp_path, "blur.png", (1600, 1200), blur_sigma=20)
    doc = _stored_doc(
        file_name="blur.png",
        stored_path=str(path),
        extension=".png",
        mime_type="image/png",
        sha256="blurhash",
    )
    db_session.add(doc)
    db_session.commit()

    result = asyncio.get_event_loop().run_until_complete(_run_pipeline(db_session, doc, monkeypatch))
    assert result.verification["status"] == "BLURRY"
    assert not result.raw_text


def test_wrong_document_detected_after_ocr(db_session, tmp_path, monkeypatch):
    import asyncio

    path = _write_synthetic_image(tmp_path, "sharp.png", (1800, 1400), blur_sigma=0)

    class _Classify:
        async def classify(self, text):
            return {"doc_type": "resume", "confidence": 0.9, "reason": "test"}

    async def _aresult(path=None, extension=None, **kw):
        return OCRResult(text="CURRICULUM VITAE of Ali Raza", provider="test", confidence=0.9)

    import app.services.processing as processing

    monkeypatch.setattr(processing.ocr_pipeline, "extract", _aresult)
    monkeypatch.setattr(processing.classification, "classify", _Classify().classify)

    doc = _stored_doc(
        file_name="actually_resume.png",
        stored_path=str(path),
        extension=".png",
        mime_type="image/png",
        sha256="hash1",
        expected_doc_type="cnic",
    )
    db_session.add(doc)
    db_session.commit()

    result = asyncio.get_event_loop().run_until_complete(processing.process_document(db_session, doc, expected_type="cnic"))
    assert result.verification["status"] == "WRONG DOCUMENT TYPE"
    assert result.doc_type == "resume"
    assert result.expected_doc_type == "cnic"


# --- Inconsistency detection ----------------------------------------------------

from app.services import verification  # noqa: E402


class _FakeDoc:
    def __init__(self, doc_id, file_name, doc_type, extracted, status="PASSED"):
        self.id = doc_id
        self.file_name = file_name
        self.doc_type = doc_type
        self.extracted = extracted
        self.verification = {"status": status, "issues": []}

    @property
    def verification_status(self):
        return self.verification.get("status", "PENDING")


def test_inconsistency_name_mismatch_detected():
    docs = [
        _FakeDoc(1, "cnic.pdf", "cnic", {"full_name": "Ayesha Khan", "cnic": "35202-1234567-1"}),
        _FakeDoc(2, "degree.pdf", "degree", {"full_name": "Ali Raza", "cnic": "35202-1234567-1"}),
    ]
    incs = verification.detect_inconsistencies(docs)
    fields = [i["field"] for i in incs]
    assert "full_name" in fields
    assert "cnic" not in fields  # both agree on the CNIC number


def test_inconsistency_rejected_uploads_ignored():
    docs = [
        _FakeDoc(1, "cnic.pdf", "cnic", {"full_name": "Ayesha Khan"}, status="PASSED"),
        _FakeDoc(2, "bad.pdf", "resume", {}, status="DUPLICATE"),
    ]
    incs = verification.detect_inconsistencies(docs)
    assert incs == []


def test_inconsistency_missing_fields_not_flagged():
    docs = [
        _FakeDoc(1, "cnic.pdf", "cnic", {"full_name": "Ayesha Khan"}),
        _FakeDoc(2, "transcript.pdf", "transcript", {"university": "UOK"}),  # no full_name
    ]
    incs = verification.detect_inconsistencies(docs)
    assert incs == []


def test_inconsistency_cnic_mismatch_detected():
    docs = [
        _FakeDoc(1, "cnic.pdf", "cnic", {"full_name": "Ali Raza", "cnic": "35202-1234567-1"}),
        _FakeDoc(2, "degree.pdf", "degree", {"full_name": "Ali Raza", "cnic": "35202-7654321-3"}),
    ]
    incs = verification.detect_inconsistencies(docs)
    fields = [i["field"] for i in incs]
    assert "cnic" in fields
    assert "full_name" not in fields


def test_apply_inconsistencies_marks_documents():
    docs = [
        _FakeDoc(1, "cnic.pdf", "cnic", {"full_name": "Ayesha Khan"}),
        _FakeDoc(2, "degree.pdf", "degree", {"full_name": "Ali Raza"}),
    ]
    incs = verification.detect_inconsistencies(docs)
    verification.apply_inconsistencies(docs, incs)
    assert docs[0].verification["status"] == "INCONSISTENCY DETECTED"
    assert docs[1].verification["status"] == "INCONSISTENCY DETECTED"
    messages = [i["message"] for i in docs[0].verification["issues"]]
    assert any("Name mismatch" in m for m in messages)


# --- Coverage excludes rejected uploads ------------------------------------------

from app.services.coverage import compute_coverage  # noqa: E402


def test_coverage_ignores_rejected_uploads():
    # CNIC upload was rejected as BLURRY -> it never satisfies the CNIC slot.
    docs = [
        _FakeDoc(1, "resume.pdf", "resume", {}, status="PASSED"),
        _FakeDoc(2, "cnic.png", "cnic", {}, status="BLURRY"),
        _FakeDoc(3, "transcript.pdf", "transcript", {}, status="FLAGGED"),
    ]
    res = compute_coverage(docs)
    assert res["missing_documents"] == ["cnic", "offer_letter", "degree"]
    assert res["coverage"] == 0.4


def test_coverage_wrong_document_does_not_satisfy_slot():
    docs = [
        _FakeDoc(1, "resume.pdf", "resume", {}, status="WRONG DOCUMENT TYPE"),
    ]
    res = compute_coverage(docs)
    assert res["missing_documents"] == ["resume", "cnic", "offer_letter", "degree", "transcript"]
    assert res["coverage"] == 0.0


def test_coverage_flagged_and_failed_still_present():
    docs = [
        _FakeDoc(1, "resume.pdf", "resume", {}, status="FLAGGED"),
        _FakeDoc(2, "cnic.png", "cnic", {}, status="FAILED"),
    ]
    res = compute_coverage(docs)
    assert res["missing_documents"] == ["offer_letter", "degree", "transcript"]
