"""Tesseract OCR wrapper.

Kept deliberately small and standalone: the blocking `image_to_string` call is
the unit the processing layer hands to a worker thread. Swapping in a different
OCR backend later means touching only this file.
"""
from __future__ import annotations

from pathlib import Path

import pytesseract
from PIL import Image

from config import settings

# Allow pointing at a non-PATH tesseract binary (common on Windows).
if settings.tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd


class OCRUnavailable(RuntimeError):
    """Raised when the tesseract binary cannot be found."""


def is_available() -> bool:
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _clean(raw: str) -> str:
    lines = [ln.strip() for ln in raw.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


def extract_text_from_image(img: Image.Image) -> str:
    """Run OCR on an already-open PIL image. Raises OCRUnavailable if the
    tesseract binary is missing; other exceptions propagate."""
    try:
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        return _clean(pytesseract.image_to_string(img))
    except pytesseract.TesseractNotFoundError as exc:  # type: ignore[attr-defined]
        raise OCRUnavailable(str(exc)) from exc


def extract_text(image_path: str | Path) -> str:
    """Run OCR on an image file path. Raises OCRUnavailable if tesseract
    is not installed; other exceptions propagate to the caller."""
    with Image.open(image_path) as img:
        return extract_text_from_image(img)
