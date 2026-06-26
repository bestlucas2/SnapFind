"""Upload + analyze endpoints: validate, store, hash, dedupe, enqueue OCR.

`/upload/analyze` is a stateless helper that OCRs the dropped images on the fly
and returns suggested tags + a category so the user can review them in the
preview before committing the upload.
"""
from __future__ import annotations

import io
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import require_user, verify_csrf
from config import settings
from database import get_db
from models import Screenshot, User
from services import categorize, ocr, processing
from services.hashing import perceptual_hash
from services.tagging import generate_tags, normalize_tag
from templating import base_context, templates
from utils.files import dimensions_from_bytes, make_thumbnail, save_upload

router = APIRouter()


def _split_tags(raw: str) -> list[str]:
    out: list[str] = []
    for part in (raw or "").split(","):
        name = normalize_tag(part)
        if name and name not in out:
            out.append(name)
    return out


# Defined as a sync `def` (not async) so FastAPI runs it in a worker thread.
# The OCR call is blocking + CPU-bound; running it on the event loop would stall
# every other request (including Render's health check) until it finishes.
@router.post("/upload/analyze", dependencies=[Depends(verify_csrf)])
def analyze(
    files: list[UploadFile] = File(...),
    user: User = Depends(require_user),
):
    """OCR the given images and suggest tags + a category (nothing persisted)."""
    texts: list[str] = []
    for f in files[:8]:
        f.file.seek(0)
        data = f.file.read()
        try:
            with Image.open(io.BytesIO(data)) as img:
                texts.append(ocr.extract_text_from_image(img))
        except ocr.OCRUnavailable:
            return JSONResponse(
                {"available": False, "suggested_tags": [], "suggested_category": None}
            )
        except Exception:
            continue

    combined = "\n".join(t for t in texts if t).strip()
    return JSONResponse(
        {
            "available": True,
            "suggested_tags": generate_tags(combined, limit=8),
            "suggested_category": categorize.categorize(combined) if combined else None,
        }
    )


# Sync `def`: this does blocking work per file (hashing, thumbnailing, and
# network uploads to Supabase Storage). FastAPI runs it in a worker thread so the
# event loop stays free to answer other requests / the health check.
@router.post("/upload", dependencies=[Depends(verify_csrf)])
def upload(
    request: Request,
    files: list[UploadFile] = File(...),
    tags: str = Form(""),
    category: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    manual_tags = _split_tags(tags)
    chosen_category = category.strip()[:40]

    created: list[Screenshot] = []
    duplicates: list[dict] = []
    skipped: list[dict] = []

    for f in files:
        name = f.filename or "screenshot"
        ext = Path(name).suffix.lower()
        if ext not in settings.allowed_extensions:
            skipped.append({"name": name, "reason": "unsupported type"})
            continue

        f.file.seek(0)
        data = f.file.read()
        if len(data) > settings.max_upload_bytes:
            skipped.append({"name": name, "reason": f"larger than {settings.max_upload_mb} MB"})
            continue

        try:
            with Image.open(io.BytesIO(data)) as probe:
                probe.verify()
            with Image.open(io.BytesIO(data)) as img:
                phash = perceptual_hash(img)
        except Exception:
            skipped.append({"name": name, "reason": "not a valid image"})
            continue

        stored = save_upload(user.id, data, ext)
        width, height = dimensions_from_bytes(data)
        thumb = make_thumbnail(user.id, stored, data)

        shot = Screenshot(
            user_id=user.id,
            filename=Path(name).stem,
            original_filename=name,
            stored_filename=stored,
            thumb_filename=thumb,
            content_type=f.content_type or "image/png",
            file_size=len(data),
            width=width,
            height=height,
            image_hash=phash,
            category=chosen_category or "Miscellaneous",
        )
        db.add(shot)
        db.flush()

        # Attach the user's manual/accepted tags now so they survive indexing.
        if manual_tags:
            processing.attach_tags(db, shot, manual_tags, auto=False)

        if phash:
            original = (
                db.execute(
                    select(Screenshot)
                    .where(
                        Screenshot.user_id == user.id,
                        Screenshot.image_hash == phash,
                        Screenshot.id != shot.id,
                        Screenshot.deleted_at.is_(None),
                    )
                    .order_by(Screenshot.created_at.asc())
                )
                .scalars()
                .first()
            )
            if original is not None:
                duplicates.append({"new": shot, "original": original})

        created.append(shot)

    db.commit()

    for shot in created:
        processing.enqueue(shot.id)

    ctx = base_context(
        request, user, db,
        created=created, duplicates=duplicates, skipped=skipped,
    )
    response = templates.TemplateResponse("partials/_upload_results.html", ctx)
    response.headers["HX-Trigger"] = "refresh-grid"
    return response
