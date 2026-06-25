"""Local object storage helpers. Files are namespaced per-user.

`<STORAGE_DIR>/<user_id>/<random>.<ext>` keeps each user's uploads isolated on
disk, mirroring the per-user-prefix pattern you'd use with S3/GCS later.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from PIL import Image

from config import settings

THUMB_MAX = (640, 640)


def user_storage_dir(user_id: int) -> Path:
    d = settings.storage_path / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def unique_name(ext: str) -> str:
    ext = ext if ext.startswith(".") else f".{ext}"
    return f"{uuid.uuid4().hex}{ext.lower()}"


def save_upload(user_id: int, data: bytes, ext: str) -> str:
    """Persist bytes, return the stored filename (not the full path)."""
    name = unique_name(ext)
    (user_storage_dir(user_id) / name).write_bytes(data)
    return name


def make_thumbnail(user_id: int, source_name: str) -> str | None:
    """Generate a JPEG thumbnail beside the original. Returns its name."""
    try:
        src = user_storage_dir(user_id) / source_name
        with Image.open(src) as img:
            img = img.convert("RGB")
            img.thumbnail(THUMB_MAX)
            thumb_name = f"thumb_{Path(source_name).stem}.jpg"
            img.save(user_storage_dir(user_id) / thumb_name, "JPEG", quality=82)
        return thumb_name
    except Exception:
        return None


def image_dimensions(user_id: int, source_name: str) -> tuple[int | None, int | None]:
    try:
        with Image.open(user_storage_dir(user_id) / source_name) as img:
            return img.width, img.height
    except Exception:
        return None, None


def abs_path(relpath: str) -> Path:
    return settings.storage_path / relpath


def remove_relpath(relpath: str | None) -> None:
    if not relpath:
        return
    try:
        (settings.storage_path / relpath).unlink(missing_ok=True)
    except Exception:
        pass
