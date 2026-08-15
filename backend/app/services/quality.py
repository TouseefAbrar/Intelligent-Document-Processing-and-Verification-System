"""Image quality + integrity analysis.

Provides the signals used by the validation gates:
  * blur estimation (Laplacian variance)              -> ``is_blurry``
  * brightness / contrast / sharpness score           -> informational metrics
  * PDF first-page render + assess                    -> quality gate for PDFs
  * QR code extraction and Error-Level Analysis       -> bonus challenges
"""
from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.core.logging import get_logger
from app.utils.images import load_image

logger = get_logger("services.quality")

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}


def _gray(path: Path):
    import numpy as np

    img = load_image(path)
    arr = np.asarray(img)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)


def _base_result() -> dict:
    return {
        "blur": 0.0,
        "brightness": 0.0,
        "contrast": 0.0,
        "width": 0,
        "height": 0,
        "quality_score": 1.0,
        "issues": [],
        "is_blurry": False,
    }


def assess_quality(path: Path) -> dict:
    """Assess an image file.

    Returns pixel metrics plus the ``is_blurry`` gate flag.
    """
    result = _base_result()
    if cv2 is None:
        result["issues"].append("opencv unavailable; quality skipped")
        return result

    try:
        img = load_image(path)
        width, height = img.size
        result["width"] = width
        result["height"] = height
        dpi = img.info.get("dpi")
        if isinstance(dpi, tuple) and dpi:
            result["dpi"] = round(float(dpi[0]), 1)

        if width == 0 or height == 0:
            result["issues"].append("empty image")
            return result

        gray = _gray(path)
        variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        brightness = float(gray.mean())
        contrast = float(gray.std())

        result["blur"] = round(variance, 2)
        result["brightness"] = round(brightness, 2)
        result["contrast"] = round(contrast, 2)

        # --- Blur gate (sharpness only, independent of size) ---
        if variance < settings.BLUR_VARIANCE_THRESHOLD:
            result["is_blurry"] = True
            result["issues"].append("Image is blurry (low edge variance)")

        # Sharpness score 0..1 (blur-derived only)
        score = 1.0
        score -= max(0.0, min(0.6, (settings.BLUR_VARIANCE_THRESHOLD - variance) / settings.BLUR_VARIANCE_THRESHOLD))
        result["quality_score"] = round(max(0.0, score), 3)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Quality assessment failed: %s", exc)
        result["issues"].append("quality check error")

    return result


def assess_pdf(path: Path) -> dict:
    """Quality-gate a PDF by rendering its first page and assessing it.

    Digital/text PDFs render with crisp edges (high variance → passes).
    Scanned PDFs are assessed like any scan. Returns the same shape as
    ``assess_quality`` with an extra ``note``.
    """
    result = _base_result()
    result["note"] = "PDF pixel quality checked via first-page render"
    try:
        import fitz

        with fitz.open(str(path)) as doc:
            if doc.page_count == 0:
                result["issues"].append("PDF contains no pages")
                return result
            page = doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(150 / 72, 150 / 72))
            tmp = path.parent / f"{path.stem}_qc.jpg"
            pix.save(str(tmp))
        try:
            result = assess_quality(tmp)
        finally:
            tmp.unlink(missing_ok=True)
        result["note"] = "PDF pixel quality checked via first-page render"
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("PDF quality check failed: %s", exc)
        result["issues"].append("PDF quality check failed")
        result["is_blurry"] = False
        return result


def detect_qr(path: Path) -> dict:
    """Detect and decode QR codes (bonus: QR verification)."""
    out = {"found": False, "data": "", "method": "opencv"}
    if cv2 is None:
        return out
    try:
        import numpy as np

        img = np.asarray(load_image(path))
        bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        detector = cv2.QRCodeDetector()
        data, points, _ = detector.detectAndDecode(bgr)
        if data:
            out["found"] = True
            out["data"] = data
    except Exception as exc:  # noqa: BLE001
        logger.warning("QR detection failed: %s", exc)
    return out


def detect_tampering(path: Path) -> dict:
    """Error-Level Analysis heuristic for tamper detection (bonus).

    Re-save at a low JPEG quality and measure the difference. Tampered
    regions typically show higher error levels than the untouched image.
    """
    out = {"detected": False, "score": 0.0, "method": "ela", "note": ""}
    if cv2 is None:
        out["note"] = "opencv unavailable"
        return out
    try:
        import io

        import numpy as np
        from PIL import Image

        img = load_image(path).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        buf.seek(0)
        resaved = Image.open(buf).convert("RGB")

        orig = np.asarray(img, dtype=np.int16)
        resv = np.asarray(resaved, dtype=np.int16)
        diff = np.abs(orig - resv)
        ela = diff * 15
        ela = np.clip(ela, 0, 255).astype(np.uint8)

        mean_ela = float(ela.mean())
        var_ela = float(ela.var())
        out["score"] = round(mean_ela, 3)
        # Heuristic thresholds tuned for typical scans/documents.
        if mean_ela > 4.0 and var_ela > 40.0:
            out["detected"] = True
            out["note"] = "Unusual error-level variation — possible tampering"
        else:
            out["note"] = "No obvious tampering signature detected"
    except Exception as exc:  # noqa: BLE001
        logger.warning("ELA failed: %s", exc)
        out["note"] = "ELA skipped"
    return out


def estimate_dpi(path: Path) -> float | None:
    try:
        img = load_image(path)
        return img.info.get("dpi", (72, 72))[0]
    except Exception:  # noqa: BLE001
        return None
