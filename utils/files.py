"""File helpers built on the pluggable storage backend (local or Supabase).

Paths are per-user relative: "<user_id>/<filename>". Image bytes are passed
around in memory so the same code works whether files live on local disk or in
Supabase Storage (where there is no local path to open).
"""
from __future__ import annotations

import io
import uuid
from pathlib import Path

from PIL import Image

from services.storage import get_storage

THUMB_MAX = (640, 640)

_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def content_type_for(ext: str) -> str:
    return _CONTENT_TYPES.get(ext.lower(), "application/octet-stream")


def unique_name(ext: str) -> str:
    ext = ext if ext.startswith(".") else f".{ext}"
    return f"{uuid.uuid4().hex}{ext.lower()}"


def save_upload(user_id: int, data: bytes, ext: str) -> str:
    """Store raw bytes, return the stored filename (relative to the user dir)."""
    name = unique_name(ext)
    get_storage().put(f"{user_id}/{name}", data, content_type_for(ext))
    return name


def make_thumbnail(user_id: int, source_name: str, data: bytes) -> str | None:
    """Build a JPEG thumbnail from the original bytes and store it."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = img.convert("RGB")
            img.thumbnail(THUMB_MAX)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=82)
        thumb_name = f"thumb_{Path(source_name).stem}.jpg"
        get_storage().put(f"{user_id}/{thumb_name}", buf.getvalue(), "image/jpeg")
        return thumb_name
    except Exception:
        return None


def dimensions_from_bytes(data: bytes) -> tuple[int | None, int | None]:
    try:
        with Image.open(io.BytesIO(data)) as img:
            return img.width, img.height
    except Exception:
        return None, None


def get_bytes(relpath: str | None) -> bytes | None:
    if not relpath:
        return None
    return get_storage().get(relpath)


def remove_relpath(relpath: str | None) -> None:
    if relpath:
        get_storage().delete(relpath)
