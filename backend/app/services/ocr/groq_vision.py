"""Vision-LLM OCR using Groq image models.

Great for scanned documents and gives multi-language support for free (bonus
challenge). The document image is base64-encoded and sent to a Groq vision
model which returns verbatim transcription.
"""
from __future__ import annotations

import base64
from pathlib import Path

from app.config import settings
from app.services.ai.groq_client import groq_client
from app.services.ai.prompts import OCR_TRANSCRIPTION_INSTRUCTIONS
from app.services.ocr.base import BaseOCREngine, OCRResult
from app.utils.images import image_to_jpeg_base64

from app.core.logging import get_logger

logger = get_logger("ocr.groq")

DEFAULT_LANG_INSTRUCTION = (
    "Transcribe the text in the language(s) shown in the document (Urdu, Arabic, "
    "Roman Urdu and English are all supported). "
)


class GroqVisionEngine(BaseOCREngine):
    provider_name = "groq-vision"

    async def available(self) -> bool:
        if not groq_client.available:
            return False
        return await groq_client.vision_available()

    async def extract(self, path: Path, pages: list[Path] | None = None, **kwargs) -> OCRResult:
        if not groq_client.available:
            raise RuntimeError("Groq API key not configured; cannot use Groq vision OCR")
        if not await self.available():
            raise RuntimeError("No Groq vision model available on this account")
        lang = kwargs.get("language", "auto")
        instruction = OCR_TRANSCRIPTION_INSTRUCTIONS
        if lang in ("auto", "multi"):
            instruction = DEFAULT_LANG_INSTRUCTION + instruction

        candidates = pages or [path]
        transcribed: list[str] = []
        for idx, page in enumerate(candidates):
            b64 = image_to_jpeg_base64(page, max_side=2048)
            resp = await groq_client.vision_ocr(b64, instruction)
            text = (resp.get("content") or "").strip()
            if text and text != "NO_TEXT_FOUND":
                transcribed.append(text)
            logger.info("Groq OCR page %d/%d chars=%d", idx + 1, len(candidates), len(text))

        full = "\n".join(transcribed).strip()
        return OCRResult(text=full, provider=self.provider_name, confidence=0.9, language=lang)


groq_vision_engine = GroqVisionEngine()
