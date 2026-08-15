"""OCR Pipeline.

High-level flow for any uploaded document:

    PDF ──> PyMuPDF text layer
              │
              └─(too little text)──> render pages ──> image OCR providers
    Image ───────────────────────────────────────────> image OCR providers

Image providers resolve by priority when OCR_PROVIDER=auto:
    1. Groq vision   (best accuracy, multi-language, requires API key)
    2. Tesseract     (local, requires system binary)
    3. EasyOCR       (local, downloads models on first run)
"""
from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.core.logging import get_logger
from app.services.ai.groq_client import groq_client
from app.services.ocr.base import OCRResult
from app.services.ocr.easyocr_engine import easyocr_engine
from app.services.ocr.groq_vision import groq_vision_engine
from app.services.ocr.pdf_text import pdf_text_engine
from app.services.ocr.tesseract_ocr import tesseract_engine
from app.utils.images import render_pdf_pages

logger = get_logger("ocr.pipeline")


class OCRPipeline:
    def __init__(self) -> None:
        self.provider = settings.OCR_PROVIDER

    def _image_provider_order(self) -> list:
        """Ordered candidate providers; the first usable one is tried first.

        EasyOCR is only used when explicitly configured (`OCR_PROVIDER=easyocr`)
        because its native stack can hard-crash on some Windows setups.
        """
        if self.provider == "groq" or self.provider == "groq-vision":
            return [groq_vision_engine]
        if self.provider == "tesseract":
            return [tesseract_engine]
        if self.provider == "easyocr":
            return [easyocr_engine]
        # auto
        order = []
        # Only try Groq vision when the account is configured with a vision
        # model that exists — otherwise skip straight to Tesseract and avoid
        # the wasted model-list network round-trip on every image.
        if settings.groq_available and groq_client.has_vision_config():
            order.append(groq_vision_engine)
        order.append(tesseract_engine)
        return order

    async def _run_image_ocr(self, path: Path, pages: list[Path], language: str) -> OCRResult:
        """Try image OCR providers in priority order, falling back on failure."""
        candidates = self._image_provider_order()
        last_error: Exception | None = None
        for engine in candidates:
            try:
                return await engine.extract(path, pages=pages, language=language)
            except Exception as exc:  # noqa: BLE001
                logger.warning("OCR provider %s failed: %s", engine.provider_name, exc)
                last_error = exc
        raise RuntimeError(
            f"No working image OCR provider. {last_error or ''} "
            "(install Tesseract, set TESSERACT_CMD, or add a Groq vision model)"
        )

    async def extract(self, path: Path, extension: str, language: str = "auto") -> OCRResult:
        if extension == ".pdf":
            result = await pdf_text_engine.extract(path)
            # Native text is sufficient for digital PDFs; otherwise OCR the scan.
            if len(result.text.strip()) >= settings.OCR_MIN_TEXT_LENGTH:
                result.language = language
                return result
            logger.info("PDF has little/native text (%d chars); running image OCR", len(result.text))
            pages = render_pdf_pages(path)
            return await self._run_image_ocr(path, pages=pages, language=language)

        return await self._run_image_ocr(path, pages=[path], language=language)


ocr_pipeline = OCRPipeline()
