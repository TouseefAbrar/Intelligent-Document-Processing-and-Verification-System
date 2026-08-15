"""Tests for required-document coverage and normalization.

Covers the single source of truth shared by the applicant checklist, the
document-coverage UI and the key-metrics aggregation:
  * doc_type normalization ("Resume" == "resume" == "RESUME", etc.)
  * per-required-doc presence ("FLAGGED" still counts as present)
  * overall coverage math (0%, 60%, 80%, 100%)
  * duplicates / unknown types never inflate coverage
  * submission list serialization includes documents + live coverage
"""
from app.api.routes.submissions import _submission_out
from app.services import verification
from app.services.coverage import compute_coverage, normalize_doc_type, required_doc_types


# --- Normalization -----------------------------------------------------------

def test_normalize_doc_type_case_and_separators():
    assert normalize_doc_type("resume") == "resume"
    assert normalize_doc_type("Resume") == "resume"
    assert normalize_doc_type("RESUME") == "resume"
    assert normalize_doc_type("offer_letter") == "offer_letter"
    assert normalize_doc_type("Offer Letter") == "offer_letter"
    assert normalize_doc_type("offer letter") == "offer_letter"
    assert normalize_doc_type("OFFER LETTER") == "offer_letter"
    assert normalize_doc_type("transcript") == "transcript"
    assert normalize_doc_type("degree") == "degree"
    assert normalize_doc_type("cnic") == "cnic"


def test_normalize_doc_type_unknown():
    assert normalize_doc_type("tax_return") == "other"
    assert normalize_doc_type("") == "other"
    assert normalize_doc_type(None) == "other"


def test_normalize_internship_letter_is_offer_letter():
    # An internship offer letter satisfies the required offer_letter slot.
    for raw in ("internship_letter", "internship letter", "internship offer", "Internship Offer Letter"):
        assert normalize_doc_type(raw) == "offer_letter", raw


# --- Helpers -----------------------------------------------------------------

class _FakeDoc:
    def __init__(self, doc_type: str, verification_status: str = "PASSED", confidence: float = 0.9):
        from datetime import datetime, timezone

        self.doc_type = doc_type
        self.id = 0
        self.file_name = f"{doc_type}.pdf"
        self.classification_confidence = 0.9
        self.ocr_confidence = 0.9
        self.language = "en"
        self.file_size = 100
        self.extracted = {}
        self.quality = {}
        self.duplicate = {"is_duplicate": False, "similarity": 0.0, "method": "dhash"}
        self.ocr_provider = "test"
        self.raw_text = "text"
        self.created_at = datetime.now(timezone.utc)
        self.verification = {
            "status": verification_status,
            "confidence": confidence,
            "issues": [],
            "recommended_actions": [],
        }


def _docs(types_with_status: list[tuple[str, str]]) -> list[_FakeDoc]:
    return [_FakeDoc(t, s) for t, s in types_with_status]


def _make_submission(docs: list[_FakeDoc], **overrides):
    from datetime import datetime, timezone

    class _FakeSubmission:
        def __init__(self):
            self.id = 1
            self.applicant_ref = ""
            self.status = "FAILED"
            self.completeness_score = 0.0
            self.overall_confidence = 0.0
            self.missing_documents = []
            self.duplicate_documents = []
            self.summary = {}
            self.report_url = ""
            self.created_at = datetime.now(timezone.utc)
            self.documents = docs
            for k, v in overrides.items():
                setattr(self, k, v)

    return _FakeSubmission()


# --- Coverage math (Cases 1-5) -----------------------------------------------

def test_coverage_all_five_present():
    res = compute_coverage(_docs([
        ("resume", "PASSED"), ("cnic", "PASSED"), ("offer_letter", "PASSED"),
        ("degree", "PASSED"), ("transcript", "PASSED"),
    ]))
    assert res["coverage"] == 1.0
    assert res["missing_documents"] == []
    for d in res["documents"]:
        assert d["present"] is True and d["rate"] == 1.0 and d["missing_count"] == 0


def test_coverage_four_of_five_with_flagged_counted():
    # Transcript is FLAGGED but present — it must count toward coverage.
    res = compute_coverage(_docs([
        ("resume", "PASSED"), ("cnic", "PASSED"), ("offer_letter", "PASSED"),
        ("transcript", "FLAGGED"),
    ]))
    assert res["coverage"] == 0.8
    assert res["missing_documents"] == ["degree"]
    by_type = {d["doc_type"]: d for d in res["documents"]}
    assert by_type["degree"]["present"] is False
    assert by_type["degree"]["rate"] == 0.0
    assert by_type["degree"]["missing_count"] == 1
    assert by_type["transcript"]["present"] is True
    assert by_type["transcript"]["rate"] == 1.0


def test_coverage_three_of_five():
    res = compute_coverage(_docs([
        ("resume", "PASSED"), ("cnic", "PASSED"), ("transcript", "FLAGGED"),
    ]))
    assert res["coverage"] == 0.6
    assert res["missing_documents"] == ["offer_letter", "degree"]


def test_coverage_zero_of_five():
    res = compute_coverage([])
    assert res["coverage"] == 0.0
    assert len(res["missing_documents"]) == len(required_doc_types()) == 5


# --- Edge cases (6-7) --------------------------------------------------------

def test_coverage_duplicate_resume_counts_once():
    res = compute_coverage(_docs([
        ("resume", "PASSED"), ("resume", "PASSED"), ("cnic", "PASSED"),
        ("offer_letter", "PASSED"), ("transcript", "FLAGGED"),
    ]))
    assert res["coverage"] == 0.8
    assert res["missing_documents"] == ["degree"]


def test_coverage_unknown_document_does_not_satisfy():
    res = compute_coverage(_docs([
        ("resume", "PASSED"), ("cnic", "PASSED"), ("offer_letter", "PASSED"),
        ("transcript", "FLAGGED"), ("other", "FAILED"),
    ]))
    assert res["coverage"] == 0.8
    assert res["missing_documents"] == ["degree"]


def test_coverage_internship_letter_satisfies_offer_letter():
    # The AI classifies internship offer letters as internship_letter; it must
    # still satisfy the required offer_letter slot.
    res = compute_coverage(_docs([
        ("resume", "PASSED"), ("cnic", "PASSED"), ("internship_letter", "PASSED"),
        ("transcript", "FLAGGED"),
    ]))
    assert res["coverage"] == 0.8
    assert res["missing_documents"] == ["degree"]


# --- Verification engine integration -------------------------------------------

def test_submission_verification_uses_coverage_with_flagged_present():
    res = verification.compute_submission_verification(_docs([
        ("resume", "PASSED"), ("cnic", "PASSED"), ("offer_letter", "PASSED"),
        ("transcript", "FLAGGED"),
    ]))
    assert res["completeness_score"] == 0.8
    assert res["missing_documents"] == ["degree"]
    assert res["status"] == "FAILED"  # missing degree -> not auto-approvable


def test_submission_verification_normalizes_doc_type_variants():
    res = verification.compute_submission_verification(_docs([
        ("Resume", "PASSED"), ("CNIC", "PASSED"), ("Offer Letter", "PASSED"),
        ("Transcript", "FLAGGED"),
    ]))
    assert res["completeness_score"] == 0.8
    assert res["missing_documents"] == ["degree"]


# --- API serialization ---------------------------------------------------------

def test_submission_list_out_includes_documents_and_live_coverage():
    docs = _docs([
        ("resume", "PASSED"), ("cnic", "PASSED"), ("offer_letter", "PASSED"),
        ("transcript", "FLAGGED"),
    ])
    sub = _make_submission(
        docs,
        # stale snapshot: old 4-doc config produced 0.75 / wrong status
        completeness_score=0.75,
        status="FLAGGED",
        missing_documents=["degree"],
        duplicate_documents=[],
    )
    out = _submission_out(sub, include_details=False)
    # Root-cause fix: the list response must carry the documents.
    assert len(out["documents"]) == 4
    assert [d["doc_type"] for d in out["documents"]] == [
        "resume", "cnic", "offer_letter", "transcript",
    ]
    # Live aggregation overrides the stale snapshot.
    assert out["completeness_score"] == 0.8
    assert out["missing_documents"] == ["degree"]
    assert out["status"] == "FAILED"
    assert out["duplicate_documents"] == []


def test_submission_detail_out_keeps_full_documents():
    docs = _docs([("resume", "PASSED")])
    sub = _make_submission(docs)
    out = _submission_out(sub, include_details=True)
    assert len(out["documents"]) == 1
    assert out["documents"][0]["doc_type"] == "resume"
    assert "verification" in out["documents"][0]
