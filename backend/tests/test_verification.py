"""Unit tests for the rule-based verification and extraction layers.

These run without any network / API key, so they are safe for CI.
"""
import asyncio
import tempfile
from pathlib import Path

from app.services import classification, extraction, verification
from app.services.duplicates import similarity
from app.services.processing import rule_based_summary
from app.services.reporting import build_pdf_report

SAMPLE_RESUME = """CURRICULUM VITAE
Name: Ali Raza
Email: ali.raza@example.com
Phone: 0300-1234567
Professional Summary: AI Engineer with 3 years of experience.
Skills: Python, FastAPI, Docker, Machine Learning, NLP
Work Experience: ML Engineer at TechSoft (2023-2024)"""

SAMPLE_CNIC = """ISLAMIC REPUBLIC OF PAKISTAN
NATIONAL IDENTITY CARD
CNIC No: 35202-1234567-1
Name: Ayesha Khan
Date of Birth: 15-08-1998"""

SAMPLE_OFFER = """EZITECH INSTITUTE
OFFER LETTER
Dear Ali Raza,
We are pleased to offer you the position of Machine Learning Intern.
Company: Ezitech Institute
Joining date: 01 September 2026
Annual CTC: PKR 500,000"""


def test_keyword_classification_resume():
    result = classification.keyword_classify(SAMPLE_RESUME)
    assert result["doc_type"] == "resume"


def test_keyword_classification_offer_letter():
    result = classification.keyword_classify(SAMPLE_OFFER)
    assert result["doc_type"] == "offer_letter"


def test_keyword_classification_transcript_not_degree():
    result = classification.keyword_classify(SAMPLE_TRANSCRIPT)
    assert result["doc_type"] == "transcript"


def test_keyword_classification_real_transcript_not_degree():
    text = """UNIVERSITY OF KARACHI
TRANSCRIPT OF RECORDS
Name: ANAS KHAN
Program: Bachelor of Science in Artificial Intelligence
Semester: Fall-2023
Course: Machine Learning
Credit Hours: 3
Grade: A
CGPA: 3.64 / 4.00"""
    result = classification.keyword_classify(text)
    assert result["doc_type"] == "transcript"


def test_keyword_classification_degree_stays_degree():
    text = """UNIVERSITY OF KARACHI
CONVOCATION 2023
This is to certify that ANAS KHAN has been awarded the degree of
Bachelor of Science in Artificial Intelligence."""
    result = classification.keyword_classify(text)
    assert result["doc_type"] == "degree"


def test_regex_extraction_offer_letter():
    data = extraction.regex_extract(SAMPLE_OFFER, "offer_letter")
    assert data["position"] == "Machine Learning Intern"
    assert data["issuer"] == "Ezitech Institute"


def test_regex_extraction_email_and_phone():
    data = extraction.regex_extract(SAMPLE_RESUME, "resume")
    assert data["email"] == "ali.raza@example.com"
    assert data["phone"] == "0300-1234567"


def test_regex_extraction_cnic():
    data = extraction.regex_extract(SAMPLE_CNIC, "cnic")
    assert data["cnic"] == "35202-1234567-1"
    assert data["full_name"] == "Ayesha Khan"


SAMPLE_REAL_RESUME = """TOUSEEF ABRAR
https://www.linkedin.com/in/touseef-abrar-29114439b/
malak.touseef012@gmail.com   +923438516207
Enthusiastic Artificial Intelligence undergraduate with a strong foundation in
programming, Machine Learning, Deep Learning, NLP, Cyber Security and
data-driven problem solving."""


def test_regex_extraction_leading_line_resume_name():
    data = extraction.regex_extract(SAMPLE_REAL_RESUME, "resume")
    assert data["full_name"] == "Touseef Abrar"
    assert data["email"] == "malak.touseef012@gmail.com"
    assert data["phone"] == "+923438516207"


SAMPLE_REAL_OFFER = """From M/S Ezitech
Institute Amna Plaza
Peshawar Road
Date: 07-Jul-2026
To Whom IT May Concern
Touseef Abrar
Intern-ID-ETI-31277-26/31277
Internship offer
Joining Date: 06-Jul-2026
Ending Date: 04-Sep-2026
Dear Touseef Abrar,
We are delighted to extend an Onsite internship offer to you for the position
of Artificial intelligence at Ezitech Institute. If you have any questions about
this offer, please contact Kashif Saeed at 0337 7777860."""


def test_regex_extraction_real_offer_letter():
    data = extraction.regex_extract(SAMPLE_REAL_OFFER, "offer_letter")
    assert data["full_name"] == "Touseef Abrar"
    assert data["position"] == "Artificial intelligence"
    assert data["issuer"] == "Ezitech Institute"
    assert data["joining_date"] == "06-Jul-2026"
    assert data["ending_date"] == "04-Sep-2026"
    assert data["document_number"] == "ETI-31277-26/31277"
    assert "institute_phone" in data


SAMPLE_REAL_CNIC = """ISLAMIC REPUBLIC OF PAKISTAN Resident of AJK State
Name
Touseef Abrar
fatherName
Abrar Ahmed
M Pakistan
81203-8463357-1 | 01.03.2004
Date of Issue | Date of Expiry
23.01.2023 23.01.2033"""


def test_regex_extraction_real_cnic_positional_dates():
    data = extraction.regex_extract(SAMPLE_REAL_CNIC, "cnic")
    assert data["cnic"] == "81203-8463357-1"
    assert data["full_name"] == "Touseef Abrar"
    assert data["father_name"] == "Abrar Ahmed"
    assert data["date_of_birth"] == "2004-03-01"
    assert data["issue_date"] == "2023-01-23"
    assert data["expiry_date"] == "2033-01-23"
    assert data["is_verified"] is True
    assert "phone" not in data


SAMPLE_TRANSCRIPT = """S.No.: 01
Date: 07-Aug-2026
Registration No.: 5111323034
Name: ANAS KHAN
Batch: Fall-2023
Program: Bachelor of Science in Artificial Intelligence
CGPA: 3.64 / 4.00"""


def test_regex_extraction_transcript_no_phone():
    data = extraction.regex_extract(SAMPLE_TRANSCRIPT, "transcript")
    assert data["full_name"] == "Anas Khan"
    assert data["document_number"] == "5111323034"
    assert data["cgpa"] == 3.64
    assert data["is_verified"] is False
    assert "phone" not in data


def test_duplicate_similarity():
    assert similarity("abcdef", "abcdef") == 1.0
    assert similarity("abcdef", "abcdeg") < 1.0


class _FakeDoc:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_verification_rules_pass_for_complete_resume():
    doc = _FakeDoc(
        raw_text=SAMPLE_RESUME,
        ocr_confidence=0.9,
        quality={"issues": []},
        duplicate={"is_duplicate": False, "similarity": 0.0},
        doc_type="resume",
        extracted={
            "full_name": "Ali Raza", "email": "ali.raza@example.com",
            "phone": "0300-1234567", "skills": ["Python"],
        },
    )
    res = verification.verify_document_rules(doc)
    assert res["status"] == "PASSED"


def test_verification_rules_fail_on_duplicate():
    doc = _FakeDoc(
        raw_text=SAMPLE_RESUME,
        ocr_confidence=0.9,
        quality={"issues": []},
        duplicate={"is_duplicate": True, "similarity": 0.99},
        doc_type="resume",
        extracted={"full_name": "Ali Raza"},
    )
    res = verification.verify_document_rules(doc)
    assert res["status"] == "FAILED"


class _FakeSubmission:
    def __init__(self, documents):
        self.documents = documents


def test_rule_based_summary_is_complete():
    docs = [
        _FakeDoc(
            raw_text=SAMPLE_RESUME, file_name="resume.pdf", doc_type="resume",
            verification={"status": "PASSED", "issues": []},
            extracted={"full_name": "Ali Raza", "email": "ali.raza@example.com"},
        ),
        _FakeDoc(
            raw_text=SAMPLE_CNIC, file_name="cnic.jpg", doc_type="cnic",
            verification={
                "status": "FLAGGED",
                "issues": [{"severity": "critical", "message": "CNIC expiry date is very close"}],
            },
            extracted={"cnic": "35202-1234567-1", "full_name": "Ali Raza"},
        ),
    ]
    res = {
        "status": "FLAGGED",
        "completeness_score": 0.75,
        "overall_confidence": 0.8,
        "missing_documents": ["degree"],
        "duplicate_documents": [],
        "critical_documents": 0,
        "flagged_documents": 1,
        "inconsistency_documents": 0,
    }
    summary = rule_based_summary(_FakeSubmission(docs), res, [])
    for key in ("overall_comment", "highlights", "concerns", "recommended_action", "applicant_name"):
        assert key in summary
    assert summary["applicant_name"] == "Ali Raza"
    assert summary["recommended_action"] == "REVIEW"
    assert any("Degree document is missing" in c for c in summary["concerns"])
    assert any("expiry" in c.lower() for c in summary["concerns"])


def test_pdf_report_renders_every_field_and_section():
    extracted = {f"field_{i}": f"value number {i}" for i in range(1, 30)}
    report = {
        "report_id": "EEF-00001",
        "generated_at": "2026-08-14T10:00:00+00:00",
        "submission_id": 1,
        "applicant_ref": "AP-001",
        "status": "FLAGGED",
        "completeness_score": 0.75,
        "overall_confidence": 0.8,
        "missing_documents": ["degree"],
        "duplicate_documents": [],
        "summary": {
            "overall_comment": "x" * 600,
            "recommended_action": "REVIEW",
            "highlights": ["One"],
            "concerns": ["Two"],
            "inconsistencies": [
                {"field": "phone", "field_label": "Phone", "document_a": "a.pdf", "value_a": "1", "document_b": "b.pdf", "value_b": "2"}
            ],
        },
        "documents": [
            {
                "id": 1, "file_name": "a.pdf", "doc_type": "resume", "doc_type_label": "Resume",
                "classification_confidence": 0.9, "ocr_confidence": 0.9, "ocr_provider": "tesseract",
                "language": "en", "status": "PASSED", "extracted": extracted,
                "issues": [{"severity": "info", "message": "msg"}],
                "recommended_actions": [], "quality": {}, "duplicate": {},
            }
        ],
    }
    with tempfile.TemporaryDirectory() as d:
        dest = str(Path(d) / "report.pdf")
        build_pdf_report(report, dest)
        pdf = Path(dest)
        assert pdf.exists() and pdf.stat().st_size > 1000
        from pypdf import PdfReader
        reader = PdfReader(str(pdf))
        assert len(reader.pages) >= 2
        text = "\n".join(p.extract_text() or "" for p in reader.pages)
        for needle in (
            "Cross-Document Inconsistencies",
            "Highlights",
            "Concerns",
            "value number 29",
            "x" * 40,
        ):
            assert needle in text, f"missing in PDF text: {needle!r}"
