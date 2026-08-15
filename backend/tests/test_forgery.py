"""Unit tests for the fake / forged document detection service.

These run without any network / API key, so they are safe for CI.
"""
import asyncio
import tempfile
from pathlib import Path

from app.services import forgery
from app.services.verification import verify_document_rules


def _make_image(path: Path, text: str = "DOCUMENT TEXT", size=(600, 800), fmt="PNG", pnginfo=None):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(text.splitlines()):
        draw.text((40, 60 + i * 40), line, fill="black")
    img.save(str(path), fmt, pnginfo=pnginfo)


def _tmp_path(name: str) -> Path:
    d = tempfile.mkdtemp(prefix="forgery_test_")
    return Path(d) / name


# --- Content validation -----------------------------------------------------

def test_content_signal_detects_fake_markers():
    res = forgery.content_signal("cnic", {}, "ISLAMIC REPUBLIC OF PAKISTAN SAMPLE VOID")
    assert res["score"] >= 0.85
    assert res["result"] == "suspicious"
    assert res.get("decisive") is True


def test_content_signal_accepts_clean_document():
    res = forgery.content_signal(
        "cnic",
        {"cnic": "35202-1234567-1", "issue_date": "2020-01-01", "expiry_date": "2030-01-01"},
        "NATIONAL IDENTITY CARD",
    )
    assert res["result"] == "clear"
    assert res["score"] == 0.0


def test_content_signal_rejects_invalid_cnic_format():
    res = forgery.content_signal("cnic", {"cnic": "1234-567-8"}, "")
    assert res["score"] >= 0.55


def test_content_signal_rejects_impossible_dates():
    res = forgery.content_signal(
        "cnic",
        {"date_of_birth": "2005-06-01", "issue_date": "1999-01-01"},
        "",
    )
    assert res["score"] >= 0.5


# --- Metadata forensics -----------------------------------------------------

def test_metadata_signal_detects_editing_software():
    from PIL import PngImagePlugin

    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text("Software", "Adobe Photoshop 23.0")
    path = _tmp_path("ps.png")
    _make_image(path, pnginfo=pnginfo)
    res = forgery._metadata_signal(path)
    assert res["result"] == "warning"
    assert res["score"] >= 0.4
    assert "photoshop" in res["detail"].lower()


def test_metadata_signal_clean():
    path = _tmp_path("clean.png")
    _make_image(path)
    res = forgery._metadata_signal(path)
    assert res["result"] == "clear"
    assert res["score"] == 0.0


# --- Full forensic scan -----------------------------------------------------

def test_forensic_scan_clean_image_is_green():
    path = _tmp_path("doc.png")
    _make_image(path)
    res = forgery.forensic_scan(path)
    assert res["level"] == "GREEN"
    assert res["detected"] is False
    assert isinstance(res["signals"], list) and len(res["signals"]) >= 4
    assert "score" in res and "confidence" in res


def test_forensic_scan_jpeg_no_crash():
    path = _tmp_path("doc.jpg")
    _make_image(path, fmt="JPEG")
    res = forgery.forensic_scan(path)
    assert res["level"] in ("GREEN", "YELLOW", "RED")
    assert isinstance(res["summary"], list)


# --- Aggregation / verdict --------------------------------------------------

def test_verdict_red_with_two_strong_signals():
    signals = [
        {"name": "metadata", "label": "Meta", "score": 0.9, "result": "suspicious"},
        {"name": "ela", "label": "ELA", "score": 0.7, "result": "suspicious"},
    ]
    level, score, _ = forgery._verdict(signals)
    assert level == "RED"
    assert score >= 0.6


def test_verdict_yellow_with_single_strong_signal():
    signals = [{"name": "metadata", "label": "Meta", "score": 0.9, "result": "suspicious"}]
    level, _, _ = forgery._verdict(signals)
    assert level == "YELLOW"


def test_verdict_green_when_all_clear():
    signals = [{"name": "ela", "label": "ELA", "score": 0.0, "result": "clear"}]
    level, _, _ = forgery._verdict(signals)
    assert level == "GREEN"


def test_verdict_llm_suspicious_low_confidence_stays_green():
    # A vague SUSPICIOUS verdict (no strong signals, modest confidence) must not
    # flag a real document — this was the cause of the offer-letter false flag.
    signals = [{"name": "ela", "label": "ELA", "score": 0.4, "result": "warning"}]
    level, _, _ = forgery._verdict(signals, {"verdict": "SUSPICIOUS", "confidence": 0.6})
    assert level == "GREEN"


def test_verdict_llm_suspicious_high_confidence_is_yellow():
    signals = [{"name": "ela", "label": "ELA", "score": 0.0, "result": "clear"}]
    level, _, _ = forgery._verdict(signals, {"verdict": "SUSPICIOUS", "confidence": 0.9})
    assert level == "YELLOW"


def test_dedup_signals_keeps_first_of_each_name():
    signals = [
        {"name": "metadata", "label": "A", "score": 0.0, "result": "clear"},
        {"name": "metadata", "label": "B", "score": 0.0, "result": "clear"},
        {"name": "ela", "label": "C", "score": 0.0, "result": "clear"},
    ]
    out = forgery._dedup_signals(signals)
    assert [s["name"] for s in out] == ["metadata", "ela"]


def test_combine_signals_content_marker_pushes_to_red():
    path = _tmp_path("doc.png")
    _make_image(path)
    scan = forgery.forensic_scan(path)
    assert scan["level"] == "GREEN"
    content = forgery.content_signal("cnic", {}, "FAKE DOCUMENT SAMPLE")
    merged = forgery.combine_signals(scan, content)
    assert merged["level"] == "RED"


def test_apply_llm_forged_verdict_is_red():
    path = _tmp_path("doc.png")
    _make_image(path)
    scan = forgery.forensic_scan(path)
    result = forgery.apply_llm(scan, {"verdict": "FORGED", "confidence": 0.85, "notes": ["x"]})
    assert result["level"] == "RED"
    assert result["engine"] == "heuristics+llm"
    assert result["llm"]["verdict"] == "FORGED"


# --- Verification integration -----------------------------------------------

class _FakeDoc:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_verify_document_rules_flags_yellow_forgery():
    doc = _FakeDoc(
        raw_text="CURRICULUM VITAE\nName: Ali Raza\nEmail: a@b.com",
        ocr_confidence=0.9,
        quality={"issues": []},
        duplicate={"is_duplicate": False, "similarity": 0.0},
        doc_type="resume",
        extracted={"full_name": "Ali Raza", "email": "a@b.com", "phone": "0300-1234567", "skills": ["Python"]},
        forgery={"level": "YELLOW", "note": "Suspicious forensic signals"},
    )
    res = verify_document_rules(doc)
    assert res["status"] == "FLAGGED"
    assert any(i["field"] == "forgery" for i in res["issues"])


def test_verify_document_rules_ignores_missing_forgery():
    doc = _FakeDoc(
        raw_text="CURRICULUM VITAE\nName: Ali Raza\nEmail: a@b.com",
        ocr_confidence=0.9,
        quality={"issues": []},
        duplicate={"is_duplicate": False, "similarity": 0.0},
        doc_type="resume",
        extracted={"full_name": "Ali Raza", "email": "a@b.com", "phone": "0300-1234567", "skills": ["Python"]},
    )
    res = verify_document_rules(doc)
    assert res["status"] == "PASSED"


# --- Rejection record -------------------------------------------------------

def test_forgery_rejection_record():
    res = forgery.forgery_rejection({"summary": ["CNIC invalid"], "engine": "heuristics"})
    assert res["status"] == "FORGERY DETECTED"
    assert res["issues"][0]["severity"] == "critical"
    assert "CNIC invalid" in res["issues"][0]["message"]


# --- Full pipeline (async, LLM skipped without a key) -----------------------

def test_analyze_forgery_pipeline_clean():
    path = _tmp_path("doc.png")
    _make_image(path)

    # Use a dedicated loop so the policy's event loop is left untouched (other
    # tests rely on asyncio.get_event_loop()).
    loop = asyncio.new_event_loop()
    try:
        res = loop.run_until_complete(
            forgery.analyze_forgery(path, "resume", {"full_name": "Ali Raza"}, "CURRICULUM VITAE")
        )
    finally:
        loop.close()
    assert res["level"] in ("GREEN", "YELLOW")
    assert res["engine"] in ("heuristics", "heuristics+llm")
