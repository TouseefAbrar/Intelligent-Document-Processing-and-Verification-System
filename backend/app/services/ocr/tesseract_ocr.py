"""Tesseract OCR provider — the reliable local engine for scanned documents.

Requires the Tesseract binary. On Windows it is auto-discovered in the
standard install paths when `TESSERACT_CMD` is not set.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from app.config import settings
from app.core.logging import get_logger
from app.services.ocr.base import BaseOCREngine, OCRResult

logger = get_logger("ocr.tesseract")

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None

_WINDOWS_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


class TesseractEngine(BaseOCREngine):
    provider_name = "tesseract"

    def resolve_binary(self) -> str | None:
        if pytesseract is None:
            return None
        cmd = settings.TESSERACT_CMD
        if cmd and cmd.lower() != "tesseract" and Path(cmd).exists():
            return cmd
        if cmd:
            try:
                pytesseract.pytesseract.tesseract_cmd = cmd
                pytesseract.get_tesseract_version()
                return cmd
            except Exception:  # noqa: BLE001
                pass
        found = shutil.which("tesseract")
        if found:
            return found
        for candidate in _WINDOWS_PATHS:
            if Path(candidate).exists():
                return candidate
        return None

    def available(self) -> bool:
        return self.resolve_binary() is not None

    async def extract(self, path: Path, pages: list[Path] | None = None, **kwargs) -> OCRResult:
        binary = self.resolve_binary()
        if binary is None:
            raise RuntimeError("Tesseract binary not found on this system")
        from PIL import Image

        pytesseract.pytesseract.tesseract_cmd = binary
        candidates = pages or [path]
        texts: list[str] = []
        for page in candidates:
            texts.append(pytesseract.image_to_string(Image.open(page)))
        return OCRResult(text="\n".join(texts).strip(), provider=self.provider_name, confidence=0.8)


tesseract_engine = TesseractEngine()
