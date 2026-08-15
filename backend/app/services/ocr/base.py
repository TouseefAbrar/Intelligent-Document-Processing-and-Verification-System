"""OCR provider abstractions.

`OCRResult` is the common output contract every engine must produce so the
rest of the pipeline (classification, extraction, verification) stays
engine-agnostic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OCRResult:
    text: str
    provider: str
    confidence: float = 0.0
    language: str = "en"
    pages: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


class BaseOCREngine:
    provider_name = "base"

    async def extract(self, path: Path, pages: list[Path] | None = None, **kwargs) -> OCRResult:
        raise NotImplementedError
