"""Export screenshots + metadata as JSON, CSV, or a ZIP bundle."""
from __future__ import annotations

import csv
import io
import json
import zipfile
from collections.abc import Sequence

from models import Screenshot
from utils.files import get_bytes

_CSV_FIELDS = [
    "id", "filename", "original_filename", "category", "collection",
    "tags", "favorite", "archived", "ocr_status", "file_size",
    "width", "height", "image_hash", "created_at", "notes", "ocr_text",
]


def _row(shot: Screenshot) -> dict:
    d = shot.to_dict()
    d["tags"] = ", ".join(d["tags"])
    return {k: d.get(k, "") for k in _CSV_FIELDS}


def to_json(screenshots: Sequence[Screenshot]) -> bytes:
    payload = {
        "count": len(screenshots),
        "screenshots": [s.to_dict() for s in screenshots],
    }
    return json.dumps(payload, indent=2, default=str).encode("utf-8")


def to_csv(screenshots: Sequence[Screenshot]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS)
    writer.writeheader()
    for shot in screenshots:
        writer.writerow(_row(shot))
    return buf.getvalue().encode("utf-8")


def to_zip(screenshots: Sequence[Screenshot]) -> bytes:
    """ZIP with original images under images/ plus metadata.json + metadata.csv."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.json", to_json(screenshots))
        zf.writestr("metadata.csv", to_csv(screenshots))
        for shot in screenshots:
            data = get_bytes(shot.storage_relpath)
            if data is not None:
                arcname = f"images/{shot.id}_{shot.original_filename}"
                zf.writestr(arcname, data)
    return buf.getvalue()
