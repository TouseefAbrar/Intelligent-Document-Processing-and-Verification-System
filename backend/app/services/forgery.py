"""Fake / forged document detection service.

Combines image-forensics heuristics, content validation and LLM augmentation
into one per-document verdict:

  * Error-Level Analysis (ELA)        - tamper fingerprint (re-save traces)
  * Metadata / EXIF forensics         - editing-software trail
  * JPEG blocking & compression       - repeated re-save artifacts
  * Block noise consistency           - spliced / pasted region detection
  * Content validation                - CNIC format, impossible dates, fake markers
  * LLM augmentation (optional)       - Groq reviews the OCR text + signals

Verdict levels (also mirrored in the UI / reports):
  GREEN  - no signs of forgery
  YELLOW - suspicious, flag for manual review
  RED    - strong forgery indicators, document is rejected

Everything here degrades gracefully: a missing dependency or an unreadable
file yields a GREEN verdict with an explanatory note, never an exception.
"""
from __future__ import annotations

import io
import json
import re
from datetime import date
from pathlib import Path

from app.config import settings
from app.core.logging import get_logger
from app.services.ai.groq_client import groq_client
from app.services.ai.prompts import FORGERY_ANALYSIS_SYSTEM, FORGERY_ANALYSIS_USER
from app.services.validation import STATUS_FORGERY_DETECTED

logger = get_logger("services.forgery")

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}

# Software that strongly indicates a document was *edited* (as opposed to a
# plain scan / camera capture). Found in EXIF "Software", PNG tEXt chunks etc.
_EDITING_KEYWORDS = (
    "photoshop",
    "adobe",
    "gimp",
    "inkscape",
    "photofiltre",
    "pixlr",
    "canva",
    "paint.net",
    "paint dot net",
    "mspaint",
    "microsoft paint",
    "paint 3d",
    "paint3d",
    "snapseed",
    "corel",
    "krita",
    "pinta",
    "photo editor",
    "photopea",
)

# Printed markers that real government/institutional documents never carry.
_FAKE_MARKERS = (
    "sample",
    "specimen",
    "void",
    "not valid for legal",
    "for demonstration",
    "demonstration only",
    "demo only",
    "example only",
    "do not accept",
    "for display only",
    "invalid document",
    "fake document",
    "not a real document",
    "for verification purposes only",
    "watermark sample",
)

_EXIF_SOFTWARE = 305
_EXIF_ARTIST = 315
_EXIF_DESCRIPTION = 270
_EXIF_COPYRIGHT = 33432
_EXIF_MAKE = 271
_EXIF_MODEL = 272

_LEVEL_NOTE = {
    "GREEN": "No forgery indicators detected.",
    "YELLOW": "Suspicious forensic signals — manual review recommended.",
    "RED": "Strong forgery indicators — document rejected.",
}


# --- Image helpers ---------------------------------------------------------

def _gray(path: Path):
    import numpy as np

    from app.utils.images import load_image

    img = load_image(path)
    return cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2GRAY)


def _render_first_page(path: Path) -> Path | None:
    """Render a PDF's first page to a JPEG so image forensics can run on it."""
    out = path.parent / f"{path.stem}_forensic.jpg"
    try:
        import fitz

        with fitz.open(str(path)) as doc:
            if doc.page_count == 0:
                return None
            pix = doc.load_page(0).get_pixmap(matrix=fitz.Matrix(150 / 72, 150 / 72))
            pix.save(str(out))
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not render PDF page for forensics: %s", exc)
        return None


# --- Individual forensic signals -------------------------------------------

def _ela_signal(path: Path) -> dict:
    """Error-Level Analysis via smooth-block consistency.

    Re-saves at low JPEG quality and measures the *spatial consistency* of the
    re-save error. A genuine scan or camera capture re-encodes uniformly — its
    smooth paper regions all show the same small error — so it stays clear even
    when the mean error is high. A spliced region retains a different
    compression history and stands out against the surrounding smooth areas.
    Only smooth blocks are compared, so text edges (which always re-save
    differently) never cause false positives.
    """
    if cv2 is None:
        return {"name": "ela", "label": "Error-Level Analysis (ELA)",
                "result": "clear", "score": 0.0, "detail": "OpenCV unavailable"}
    import numpy as np
    from PIL import Image

    with Image.open(path) as opened:
        img = opened.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    resaved = Image.open(buf).convert("RGB")

    orig = np.asarray(img, dtype=np.int16)
    resv = np.asarray(resaved, dtype=np.int16)
    diff = np.abs(orig - resv).mean(axis=2).astype(np.float32)

    gray = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2GRAY)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    edge = (np.abs(gx) + np.abs(gy)).astype(np.float32)

    h, w = diff.shape
    bs = 32
    hb, wb = h // bs, w // bs
    if hb < 4 or wb < 4:
        return {"name": "ela", "label": "Error-Level Analysis (ELA)",
                "result": "clear", "score": 0.0, "detail": "Image too small for block-based ELA"}
    crop_h, crop_w = hb * bs, wb * bs
    d_err = diff[:crop_h, :crop_w].reshape(hb, bs, wb, bs).mean(axis=(1, 3))
    e_edg = edge[:crop_h, :crop_w].reshape(hb, bs, wb, bs).mean(axis=(1, 3))

    smooth = d_err[e_edg <= np.median(e_edg)]
    if smooth.size < 8:
        return {"name": "ela", "label": "Error-Level Analysis (ELA)",
                "result": "clear", "score": 0.0, "detail": "Not enough smooth regions to compare"}
    std = float(smooth.std())
    if std < 1e-4:
        return {"name": "ela", "label": "Error-Level Analysis (ELA)",
                "result": "clear", "score": 0.0,
                "detail": "Uniform re-save error (single encode, no tamper signature)"}
    mean = float(smooth.mean())
    z = np.abs(smooth - mean) / (std + 1e-6)
    outliers = int((z > 3.0).sum())

    # Warning-only signal: ELA is unreliable on real uploads, so it corroborates
    # other evidence but never drives the verdict on its own.
    if outliers:
        score = 0.4
        detail = f"{outliers}/{smooth.size} smooth regions show inconsistent re-save error — possible pasted or re-encoded region"
        result = "warning"
    else:
        score = 0.0
        detail = "No tampering signature detected by ELA"
        result = "clear"
    return {"name": "ela", "label": "Error-Level Analysis (ELA)",
            "result": result, "score": score, "detail": detail}


def _metadata_signal(path: Path) -> dict:
    """EXIF / metadata forensics: look for an editing-software trail."""
    from PIL import Image

    haystack: list[str] = []
    with Image.open(path) as img:
        text = getattr(img, "text", None) or {}
        info = img.info or {}
        for key in ("Software", "Comment", "Description", "Artist", "Copyright",
                    "ProcessingSoftware", "Creator", "Producer"):
            value = text.get(key) or info.get(key)
            if value:
                if isinstance(value, bytes):
                    value = value.decode("utf-8", errors="ignore")
                haystack.append(str(value))
        try:
            exif = img.getexif()
        except Exception:  # noqa: BLE001
            exif = {}
        for tag, label in ((_EXIF_SOFTWARE, "Software"), (_EXIF_ARTIST, "Artist"),
                           (_EXIF_DESCRIPTION, "Description"), (_EXIF_COPYRIGHT, "Copyright"),
                           (_EXIF_MAKE, "Make"), (_EXIF_MODEL, "Model")):
            value = exif.get(tag)
            if value:
                haystack.append(f"{label}={value}")

    blob = " | ".join(haystack).lower()
    matched = [kw for kw in _EDITING_KEYWORDS if kw in blob]
    if matched:
        return {
            "name": "metadata",
            "label": "Metadata & editing trail",
            "result": "warning",
            "score": 0.5,
            "detail": f"Editing software detected in file metadata: {', '.join(matched)}",
        }
    return {
        "name": "metadata",
        "label": "Metadata & editing trail",
        "result": "clear",
        "score": 0.0,
        "detail": "No editing-software trail found in metadata",
    }


def _compression_signal(path: Path) -> dict:
    """JPEG blocking + compression level — repeated re-saves leave visible grids."""
    if cv2 is None:
        return {"name": "compression", "label": "JPEG compression artifacts",
                "result": "clear", "score": 0.0, "detail": "OpenCV unavailable"}
    import numpy as np

    gray = _gray(path)
    h, w = gray.shape
    h8, w8 = h - h % 8, w - w % 8
    if h8 < 16 or w8 < 16:
        return {"name": "compression", "label": "JPEG compression artifacts",
                "result": "clear", "score": 0.0, "detail": "Image too small for block analysis"}

    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = (np.abs(gx) + np.abs(gy)).astype(np.float32)
    m = mag[:h8, :w8]
    # Energy per (row % 8, col % 8) phase — block boundaries concentrate edges.
    grid = m.reshape(h8 // 8, 8, w8 // 8, 8).sum(axis=(0, 2))
    total = float(grid.sum())
    if total <= 0:
        return {"name": "compression", "label": "JPEG compression artifacts",
                "result": "clear", "score": 0.0, "detail": "Uniform image — nothing to measure"}
    boundary = float(grid[0, :].sum() + grid[:, 0].sum() - grid[0, 0])
    blocking = boundary / max(total - boundary, 1.0)

    try:
        bpp = path.stat().st_size / (w * h)
    except OSError:
        bpp = 0.5
    bpp_score = min(1.0, max(0.0, (0.10 - bpp) / 0.07))
    block_score = min(1.0, max(0.0, (blocking - 0.40) / 0.25))
    # Capped at the warning band: JPEG compression artifacts are common on real
    # scans/captures, so this corroborates other evidence but never escalates
    # a document on its own.
    score = round(min(0.55, 0.7 * block_score + 0.3 * bpp_score), 3)

    if score >= 0.35:
        result = "warning"
        detail = f"Moderate JPEG compression artifacts (blocking={blocking:.2f})"
    else:
        result = "clear"
        detail = f"Compression artifacts within normal range (blocking={blocking:.2f})"
    return {"name": "compression", "label": "JPEG compression artifacts",
            "result": result, "score": score, "detail": detail}


def _noise_signal(path: Path) -> dict:
    """Block-noise consistency — a spliced region has a different noise profile.

    Only *smooth* tiles (low edge energy) are compared, so text-dense blocks
    never trigger false positives: a pasted/re-encoded region shows a different
    sensor-noise level than the surrounding smooth areas.
    """
    if cv2 is None:
        return {"name": "noise", "label": "Noise consistency",
                "result": "clear", "score": 0.0, "detail": "OpenCV unavailable"}
    import numpy as np

    gray = _gray(path)
    h, w = gray.shape
    tile = 64
    th, tw = h // tile, w // tile
    if th < 3 or tw < 3:
        return {"name": "noise", "label": "Noise consistency",
                "result": "clear", "score": 0.0, "detail": "Image too small for block analysis"}

    base = cv2.GaussianBlur(gray, (5, 5), 0)
    resid = np.abs(gray.astype(np.float32) - base.astype(np.float32))
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    edge = (np.abs(gx) + np.abs(gy)).astype(np.float32)

    crop_h, crop_w = th * tile, tw * tile
    r = resid[:crop_h, :crop_w]
    e = edge[:crop_h, :crop_w]
    tiles_resid = r.reshape(th, tile, tw, tile).mean(axis=(1, 3))
    tiles_edge = e.reshape(th, tile, tw, tile).mean(axis=(1, 3))

    med_edge = float(np.median(tiles_edge))
    smooth_mask = tiles_edge <= med_edge
    smooth_noises = tiles_resid[smooth_mask]
    if smooth_noises.size < 8:
        return {"name": "noise", "label": "Noise consistency",
                "result": "clear", "score": 0.0, "detail": "Not enough smooth regions to compare"}

    std = float(smooth_noises.std())
    mean = float(smooth_noises.mean())
    if std < 1e-4:
        return {"name": "noise", "label": "Noise consistency",
                "result": "clear", "score": 0.0,
                "detail": "Uniform noise across the image (likely computer-generated)"}

    z = np.abs((smooth_noises - mean) / (std + 1e-6))
    outliers = int((z > 3.0).sum())
    total = int(smooth_noises.size)
    ratio = outliers / total
    score = round(min(1.0, ratio * 3.0), 3)

    if score >= 0.6:
        return {"name": "noise", "label": "Noise consistency",
                "result": "suspicious", "score": score,
                "detail": f"{outliers}/{total} smooth regions have inconsistent noise levels — possible spliced or pasted region"}
    if score >= 0.35:
        return {"name": "noise", "label": "Noise consistency",
                "result": "warning", "score": score,
                "detail": "Slightly inconsistent noise across smooth regions — worth a manual look"}
    return {"name": "noise", "label": "Noise consistency",
            "result": "clear", "score": score,
            "detail": "Noise is consistent across the image — no obvious spliced regions"}


def _pdf_metadata_signal(path: Path) -> dict | None:
    """PDF producer/creator trail (e.g. Photoshop PDFs)."""
    try:
        import fitz

        with fitz.open(str(path)) as doc:
            meta = doc.metadata or {}
        blob = " ".join(str(v) for v in meta.values()).lower()
        matched = [kw for kw in _EDITING_KEYWORDS if kw in blob]
        if matched:
            return {
                "name": "metadata",
                "label": "PDF metadata trail",
                "result": "warning",
                "score": 0.5,
                "detail": f"Editing software detected in PDF metadata: {', '.join(matched)}",
            }
        return {
            "name": "metadata",
            "label": "PDF metadata trail",
            "result": "clear",
            "score": 0.0,
            "detail": "No editing-software trail found in PDF metadata",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("PDF metadata scan skipped: %s", exc)
        return None


def _image_forensics(path: Path, include_compression: bool = True) -> list[dict]:
    signals: list[dict] = []
    steps = [_ela_signal, _metadata_signal]
    if include_compression:
        steps.append(_compression_signal)
    steps.append(_noise_signal)
    for step in steps:
        try:
            signals.append(step(path))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Forensic step %s failed: %s", step.__name__, exc)
    return signals


# --- Content validation ----------------------------------------------------

def content_signal(doc_type: str, extracted: dict | None, raw_text: str) -> dict:
    """Rule-based content checks: fake markers, CNIC format, impossible dates."""
    extracted = extracted or {}
    text = (raw_text or "").lower()
    detail: list[str] = []
    score = 0.0
    decisive = False

    # 1. Printed fake / sample markers (decisive when present).
    hits = [m for m in _FAKE_MARKERS if m in text]
    if hits:
        score = max(score, 0.9)
        decisive = True
        detail.append(f"Printed fake/sample markers found in text: {', '.join(hits)}")

    # 2. CNIC structural validation. OCR often inserts spaces between the
    # groups, so separators are stripped before checking the 5-7-1 digit shape.
    cnic = extracted.get("cnic")
    if cnic:
        cnic_clean = re.sub(r"\D", "", str(cnic))
        if not re.fullmatch(r"\d{5}\d{7}\d", cnic_clean):
            score = max(score, 0.6)
            detail.append(f"CNIC '{cnic}' does not match the standard 00000-0000000-0 format")
        else:
            district = int(cnic_clean[:2])
            if not 1 <= district <= 99:
                score = max(score, 0.6)
                detail.append(f"CNIC district code '{cnic_clean[:2]}' is not a valid NADRA district code")

    # 3. Date sanity (issue cannot precede birth; expiry must follow issue).
    dob, issue, expiry = (
        extracted.get("date_of_birth"),
        extracted.get("issue_date"),
        extracted.get("expiry_date"),
    )
    try:
        if issue and dob and date.fromisoformat(str(issue)) < date.fromisoformat(str(dob)):
            score = max(score, 0.65)
            detail.append("Issue date is before the date of birth — impossible for a genuine document")
    except ValueError:
        pass
    try:
        if expiry and issue and date.fromisoformat(str(expiry)) <= date.fromisoformat(str(issue)):
            score = max(score, 0.6)
            detail.append("Expiry date is not after the issue date — inconsistent")
    except ValueError:
        pass

    if score >= 0.55:
        result = "suspicious"
    elif score >= 0.35:
        result = "warning"
    else:
        result = "clear"
    return {
        "name": "content",
        "label": "Content validation",
        "result": result,
        "score": round(score, 3),
        "detail": "; ".join(detail) or "No content-level inconsistencies found",
        "decisive": decisive,
    }


# --- Verdict aggregation ---------------------------------------------------

def _verdict(signals: list[dict], llm: dict | None = None) -> tuple[str, float, float]:
    """(level, score, confidence) from the signal list (plus optional LLM verdict).

    Deliberately conservative: forensic signals (ELA, compression, noise,
    metadata trail) are *corroborating* evidence and never escalate a document
    on their own. A document is only flagged when there is concrete content
    evidence or an LLM verdict:
      * RED    — decisive content marker, >= 2 strong signals, or LLM "FORGED"
      * YELLOW — a single strong signal (malformed identity data, impossible
                 dates, heavy noise inconsistency), LLM "FORGED", or a *very
                 confident* (>= 0.85) LLM "SUSPICIOUS"
      * GREEN  — everything else (real scans and clean documents pass)
    """
    if not signals:
        return "GREEN", 0.0, 0.0

    strong = [s for s in signals if s["score"] >= settings.FORGERY_RED_THRESHOLD]
    decisive = [s for s in strong if s.get("decisive")]
    lv = (llm or {}).get("verdict", "")
    lc = float((llm or {}).get("confidence") or 0.0)

    if decisive or len(strong) >= 2 or (lv == "FORGED" and lc >= 0.75):
        level = "RED"
    elif strong or (lv == "FORGED" and lc >= 0.6) or (lv == "SUSPICIOUS" and lc >= 0.85):
        level = "YELLOW"
    else:
        level = "GREEN"

    scores = sorted([s["score"] for s in signals] + ([lc] if llm else []), reverse=True)
    score = scores[0] if scores else 0.0
    if len(scores) >= 2:
        score = min(1.0, 0.65 * scores[0] + 0.35 * scores[1])

    n = len(signals) + (1 if llm else 0)
    confidence = min(1.0, 0.35 + 0.10 * n + 0.30 * score)
    return level, round(score, 3), round(confidence, 3)


def _dedup_signals(signals: list[dict]) -> list[dict]:
    """Collapse duplicate signal names (a PDF scan can emit metadata twice)."""
    seen: set[str] = set()
    out: list[dict] = []
    for s in signals:
        name = s.get("name")
        if name in seen:
            continue
        seen.add(name)
        out.append(s)
    return out


def _build_result(signals: list[dict], llm: dict | None = None) -> dict:
    signals = _dedup_signals(signals)
    level, score, confidence = _verdict(signals, llm)
    return {
        "detected": level == "RED",
        "level": level,
        "score": score,
        "confidence": confidence,
        "engine": "heuristics+llm" if llm else "heuristics",
        "signals": signals,
        "summary": [f"{s['label']}: {s['detail']}" for s in signals],
        "note": _LEVEL_NOTE[level],
    }


# --- Public API ------------------------------------------------------------

def forensic_scan(path: Path) -> dict:
    """Image-only forensic scan (runs before OCR so forged files never reach it)."""
    signals: list[dict] = []
    suffix = str(path).lower()
    if suffix.endswith(".pdf"):
        sig = _pdf_metadata_signal(path)
        if sig:
            signals.append(sig)
        rendered = _render_first_page(path)
        if rendered:
            try:
                # Compression heuristics are skipped for our own render — it is
                # a fresh high-quality encode and would otherwise false-positive.
                signals.extend(_image_forensics(rendered, include_compression=False))
            finally:
                rendered.unlink(missing_ok=True)
    elif any(suffix.endswith(ext) for ext in IMAGE_EXTS):
        signals.extend(_image_forensics(path))
    else:
        signals.append({
            "name": "format",
            "label": "File format",
            "result": "clear",
            "score": 0.0,
            "detail": f"Forensics not applicable to {suffix or 'this file type'}",
        })
    return _build_result(signals)


def combine_signals(current: dict | None, content: dict) -> dict:
    """Merge the post-OCR content signal into the forensic pre-scan result."""
    signals = list((current or {}).get("signals") or [])
    signals = [s for s in signals if s.get("name") != "content"]
    signals = _dedup_signals(signals)
    signals.append(content)
    merged = {**(current or {}), "signals": signals}
    level, score, confidence = _verdict(signals, merged.get("llm"))
    merged.update({
        "detected": level == "RED",
        "level": level,
        "score": score,
        "confidence": confidence,
        "summary": [f"{s['label']}: {s['detail']}" for s in signals],
        "note": _LEVEL_NOTE[level],
    })
    return merged


def apply_llm(current: dict, llm: dict) -> dict:
    """Recompute the verdict after the LLM reviews the document."""
    signals = list(current.get("signals") or [])
    level, score, confidence = _verdict(signals, llm)
    notes = llm.get("notes") or []
    return {
        **current,
        "detected": level == "RED",
        "level": level,
        "score": score,
        "confidence": confidence,
        "engine": "heuristics+llm",
        "llm": llm,
        "summary": [f"{s['label']}: {s['detail']}" for s in signals] + list(notes),
        "note": _LEVEL_NOTE[level],
    }


async def llm_analysis(doc_type: str, extracted: dict | None, raw_text: str, signals: list[dict]) -> dict | None:
    """Optional Groq review of the OCR text + forensic signals for fabrication."""
    if not settings.FORGERY_LLM_ENABLED or not groq_client.available:
        return None
    try:
        sig_dump = json.dumps(
            [{k: s.get(k) for k in ("name", "label", "result", "score", "detail")} for s in signals],
            ensure_ascii=False,
        )
        resp = await groq_client.complete_json(
            FORGERY_ANALYSIS_SYSTEM,
            FORGERY_ANALYSIS_USER.format(
                doc_type=doc_type or "unknown",
                extracted=json.dumps(extracted or {}, ensure_ascii=False)[:1500],
                signals=sig_dump,
                text=(raw_text or "")[:800],
            ),
            max_tokens=500,
        )
        data = groq_client.parse_json(resp.get("content", ""))
        verdict = str(data.get("verdict", "GENUINE")).upper()
        if verdict not in ("GENUINE", "SUSPICIOUS", "FORGED"):
            verdict = "GENUINE"
        try:
            confidence = round(min(1.0, max(0.0, float(data.get("confidence") or 0.0))), 3)
        except (TypeError, ValueError):
            confidence = 0.0
        return {
            "verdict": verdict,
            "confidence": confidence,
            "notes": [str(n) for n in data.get("notes", [])][:5],
            "recommended_action": str(data.get("recommended_action", "")),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Forgery LLM analysis skipped: %s", exc)
        return None


async def analyze_forgery(path: Path, doc_type: str = "", extracted: dict | None = None, raw_text: str = "") -> dict:
    """Full pipeline helper (used by tests / direct callers)."""
    result = forensic_scan(path)
    result = combine_signals(result, content_signal(doc_type, extracted, raw_text))
    if result.get("level") == "RED":
        return result
    llm = await llm_analysis(doc_type, extracted, raw_text, result.get("signals", []))
    if llm:
        result = apply_llm(result, llm)
    return result


def forgery_rejection(forgery: dict) -> dict:
    """Build the rejection verification record for a forged document."""
    reasons = forgery.get("summary") or []
    message = "; ".join(reasons) if reasons else "Strong indicators of document forgery detected"
    return {
        "status": STATUS_FORGERY_DETECTED,
        "confidence": 0.0,
        "issues": [{"field": "forgery", "message": message, "severity": "critical"}],
        "recommended_actions": [
            "Reject this document as possibly forged",
            "Request the original physical document for manual inspection",
        ],
        "engine": forgery.get("engine", "rules"),
        "reason": message,
    }
