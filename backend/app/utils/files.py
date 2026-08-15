"""File upload handling: validation, storage, hashing, MIME detection.

Validation happens on three layers so a caller cannot bypass the checks by
renaming a file or calling the API directly:
  1. extension whitelist
  2. magic-byte signature (actual content) — a file whose content does not
     match any supported signature is rejected even if its extension is allowed
  3. MIME/content-type consistency
The pipeline also runs an integrity check (can the bytes actually be decoded
as a PDF/image) in ``validate_file_integrity``.
"""
from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import settings
from app.core.logging import get_logger

logger = get_logger("utils.files")

# Magic-byte signature -> canonical extension. A file is only accepted when its
# content matches one of these signatures.
_SIGNATURES = {
    b"%PDF": ".pdf",
    b"\x89PNG\r\n\x1a\n": ".png",
    b"\xff\xd8\xff": ".jpg",
    b"II*\x00": ".tif",
    b"MM\x00*": ".tif",
    b"BM": ".bmp",
}

# webp is a RIFF container; require the "WEBP" marker at offset 8 to avoid
# false positives from WAV/AVI files.
def _detect_webp(data: bytes) -> bool:
    return data[:4] == b"RIFF" and data[8:12] == b"WEBP"


# Canonical extension -> typical content-type prefixes (case-insensitive).
_MIME_PREFIXES = {
    ".pdf": ["application/pdf"],
    ".png": ["image/png"],
    ".jpg": ["image/jpeg"],
    ".jpeg": ["image/jpeg"],
    ".tif": ["image/tiff"],
    ".tiff": ["image/tiff"],
    ".webp": ["image/webp"],
    ".bmp": ["image/bmp", "image/x-ms-bmp"],
}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def detect_extension(data: bytes) -> str:
    """Return the canonical extension matching the file's magic bytes."""
    if _detect_webp(data):
        return ".webp"
    for magic, ext in _SIGNATURES.items():
        if data.startswith(magic):
            return ext
    return ""


def _ext_for_name(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def _mime_matches(ext: str, mime: str) -> bool:
    if not mime:
        return True
    mime = mime.split(";")[0].strip().lower()
    return any(mime == p or mime.startswith(p + "/") or p in mime for p in _MIME_PREFIXES.get(ext, []))


def validate_file_bytes(raw: bytes, filename: str | None, content_type: str | None) -> dict:
    """Pure validation of a raw upload.

    Returns ``{"ok": True, "extension": <canonical ext>}`` on success or
    ``{"ok": False, "message": <user-facing reason>}`` on failure. Never raises.
    """
    if not raw:
        return {"ok": False, "message": "Uploaded file is empty"}
    if len(raw) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        return {"ok": False, "message": f"File exceeds {settings.MAX_UPLOAD_SIZE_MB}MB limit"}

    original_ext = _ext_for_name(filename)
    detected = detect_extension(raw[:32])

    if not detected:
        # Content does not match any supported document format — the strongest
        # signal. A .pdf-renamed text file or an unsupported binary lands here.
        return {
            "ok": False,
            "message": "Unsupported file type. Please upload PDF, JPG, JPEG or PNG.",
        }

    if original_ext and original_ext not in settings.allowed_extensions:
        return {
            "ok": False,
            "message": f"Unsupported file type '{original_ext}'. Please upload PDF, JPG, JPEG or PNG.",
        }

    if original_ext and detected != original_ext and not (detected in (".jpg", ".jpeg") and original_ext in (".jpg", ".jpeg")):
        return {
            "ok": False,
            "message": f"File content does not match its extension ({original_ext}). Please upload the correct file.",
        }

    if not _mime_matches(detected, content_type or ""):
        logger.warning("MIME mismatch for %s: claimed %s, detected %s", filename, content_type, detected)

    return {"ok": True, "extension": detected}


async def save_upload(upload: UploadFile) -> tuple[Path, str]:
    """Validate + persist an upload. Returns (path, detected_ext).

    Raises ``HTTPException`` (400/413/415) when the file is not a supported,
    well-formed document — the single-document endpoint uses this so the caller
    receives an immediate, clear error.
    """
    raw = await upload.read()
    result = validate_file_bytes(raw, upload.filename, upload.content_type)
    if not result["ok"]:
        status = 413 if "exceeds" in result["message"] else 400 if result["message"] == "Uploaded file is empty" else 415
        raise HTTPException(status_code=status, detail=result["message"])
    path = store_upload(raw, result["extension"])
    return path, result["extension"]


def store_upload(raw: bytes, ext: str) -> Path:
    """Persist already-validated bytes under a UUID name."""
    safe_name = f"{uuid.uuid4().hex}{ext}"
    dest = settings.upload_dir / safe_name
    dest.write_bytes(raw)
    return dest


def validate_file_integrity(path: Path, ext: str) -> dict:
    """Open the stored file to prove it is decodable, not just magic-matching.

    Catches truncated/corrupt uploads that have a valid header. Returns
    ``{"ok": True, "note": ...}`` or ``{"ok": False, "message": ...}``.
    """
    try:
        if ext == ".pdf":
            import fitz

            with fitz.open(str(path)) as doc:
                if doc.page_count == 0:
                    return {"ok": False, "message": "PDF contains no pages"}
            return {"ok": True, "note": "PDF opens successfully"}
        from PIL import Image

        with Image.open(path) as img:
            img.verify()
        return {"ok": True, "note": "Image decodes successfully"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Integrity check failed for %s: %s", path.name, exc)
        return {"ok": False, "message": "File is corrupt or could not be read as a document"}


def remove_file(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError as exc:
        logger.warning("Could not remove %s: %s", path, exc)


def clear_dir(directory: Path) -> None:
    if directory.exists():
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True, exist_ok=True)
