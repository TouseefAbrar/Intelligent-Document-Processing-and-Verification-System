"""Image helpers used across OCR, quality checks and verification."""
from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image

from app.core.logging import get_logger

logger = get_logger("utils.images")


def load_image(path: Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def image_to_jpeg_base64(path: Path, max_side: int = 2048, quality: int = 88) -> str:
    img = load_image(path)
    img.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def image_to_ndarray(path: Path):
    """Return a BGR numpy array (OpenCV convention) for CV processing."""
    import cv2
    import numpy as np

    img = load_image(path)
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def render_pdf_pages(path: Path, dpi: int = 150, max_pages: int = 6) -> list[Path]:
    """Render a PDF's pages to JPEG images so OCR can run on them."""
    import fitz

    rendered: list[Path] = []
    with fitz.open(str(path)) as doc:
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72))
            buf = io.BytesIO(pix.tobytes("png"))
            img = Image.open(buf).convert("RGB")
            out = path.parent / f"{path.stem}_page{i + 1}.jpg"
            img.save(out, "JPEG", quality=90)
            rendered.append(out)
    return rendered
