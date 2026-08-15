"""EasyOCR provider (heavier local option, no API needed).

Activates only when installed and `OCR_PROVIDER=easyocr`. Downloads its
detection/recognition models on first use.
"""
from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.core.logging import get_logger
from app.services.ocr.base import BaseOCREngine, OCRResult

logger = get_logger("ocr.easyocr")

try:
    import easyocr
except ImportError:  # pragma: no cover
    easyocr = None

_reader = None


class EasyOCREngine(BaseOCREngine):
    provider_name = "easyocr"

    def _get_reader(self):
        global _reader  # noqa: PLW0603
        if _reader is None:
            if easyocr is None:
                raise RuntimeError("easyocr not installed. Run: pip install easyocr")
            # quantize=True uses int8 models → ~1/4 the memory of fp32.
            _reader = easyocr.Reader(settings.EASYOCR_LANGS, gpu=False, quantize=True, verbose=False)
        return _reader

    async def extract(self, path: Path, pages: list[Path] | None = None, **kwargs) -> OCRResult:
        reader = self._get_reader()
        candidates = pages or [path]
        texts: list[str] = []
        for page in candidates:
            result = reader.readtext(str(page), detail=1, paragraph=True)
            texts.append("\n".join(line[1] for line in result))
        return OCRResult(text="\n".join(texts).strip(), provider=self.provider_name, confidence=0.8)


easyocr_engine = EasyOCREngine()
