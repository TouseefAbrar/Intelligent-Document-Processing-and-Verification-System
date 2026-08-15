"""Digital-text extraction from PDFs using PyMuPDF (fitz).

Handles native (text-layer) PDFs quickly and without any ML inference.
Used as the first stage of the OCR pipeline; scanned PDFs fall through
to image OCR providers.
"""
from __future__ import annotations

from pathlib import Path

from app.core.logging import get_logger
from app.services.ocr.base import BaseOCREngine, OCRResult

logger = get_logger("ocr.pdf")

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None


class PDFTextEngine(BaseOCREngine):
    provider_name = "pymupdf"

    def extract_pages(self, path: Path) -> tuple[list[str], int]:
        """Return (per-page texts, page count)."""
        if fitz is None:
            raise RuntimeError("PyMuPDF not installed. Run: pip install pymupdf")
        texts: list[str] = []
        with fitz.open(str(path)) as doc:
            for page in doc:
                texts.append(page.get_text("text"))
        return texts, len(texts)

    async def extract(self, path: Path, pages: list[Path] | None = None, **kwargs) -> OCRResult:
        texts, count = self.extract_pages(path)
        full = "\n".join(texts).strip()
        return OCRResult(text=full, provider=self.provider_name, confidence=0.95, pages=texts)


pdf_text_engine = PDFTextEngine()
