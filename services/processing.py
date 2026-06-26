"""Background OCR/index orchestration.

Uploads return immediately; the blocking Tesseract call runs in a small thread
pool so the event loop never stalls and a bulk upload doesn't serialise into one
long line. Each job opens its own DB session (sessions aren't thread-safe).
"""
from __future__ import annotations

import io
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from PIL import Image
from sqlalchemy import select

from config import settings
from database import SessionLocal
from models import (
    MAX_TAGS,
    STATUS_FAILED,
    STATUS_INDEXED,
    STATUS_PROCESSING,
    Screenshot,
    Tag,
)
from services import categorize, ocr, tagging
from utils.files import get_bytes, remove_relpath
from utils.timeutils import utcnow

log = logging.getLogger("snapfind.processing")

_executor = ThreadPoolExecutor(
    max_workers=settings.ocr_workers, thread_name_prefix="ocr"
)


def enqueue(screenshot_id: int) -> None:
    """Schedule OCR for a screenshot off the request path."""
    _executor.submit(_run_job, screenshot_id)


def _run_job(screenshot_id: int) -> None:
    db = SessionLocal()
    try:
        shot = db.get(Screenshot, screenshot_id)
        if shot is None:
            return
        process_screenshot(db, shot)
    except Exception:  # pragma: no cover - safety net for worker threads
        log.exception("OCR job failed for screenshot %s", screenshot_id)
    finally:
        db.close()


def process_screenshot(
    db, shot: Screenshot, *, fallback: dict | None = None, commit: bool = True
) -> Screenshot:
    """Run OCR + tagging + categorisation on a single screenshot.

    `fallback` (keys: text, tags, category) is used only when the OCR engine is
    unavailable — this keeps the demo seed working without Tesseract installed.
    """
    try:
        data = get_bytes(shot.storage_relpath)
        if data is None:
            raise FileNotFoundError("stored image not found")
        with Image.open(io.BytesIO(data)) as img:
            text = ocr.extract_text_from_image(img)
        _index(db, shot, text)
    except ocr.OCRUnavailable as exc:
        if fallback is not None:
            _index(db, shot, fallback.get("text", ""), category=fallback.get("category"))
        else:
            shot.ocr_status = STATUS_FAILED
            shot.ocr_error = f"Tesseract not installed: {exc}"
    except Exception as exc:  # noqa: BLE001 - one bad image shouldn't kill a batch
        shot.ocr_status = STATUS_FAILED
        shot.ocr_error = str(exc)[:500]

    if commit:
        db.commit()
    return shot


def _index(db, shot: Screenshot, text: str, category: str | None = None) -> None:
    shot.ocr_text = text or ""

    # Respect a category the user picked at upload; only auto-categorise when
    # the screenshot still has the default/blank category.
    user_set_category = bool(shot.category) and shot.category != "Miscellaneous"
    if not user_set_category:
        shot.category = category or categorize.categorize(shot.ocr_text)

    # NOTE: tags are intentionally NOT auto-attached here. The AI only *suggests*
    # tags (see /upload/analyze); a tag is added only when the user picks it.
    shot.ocr_status = STATUS_INDEXED
    shot.ocr_error = None


def attach_tags(db, shot: Screenshot, names: list[str], *, auto: bool) -> None:
    """Get-or-create user-scoped tags by name and attach any not already set,
    up to MAX_TAGS per screenshot."""
    existing = {t.name for t in shot.tags}
    for raw in names or []:
        if len(shot.tags) >= MAX_TAGS:
            break
        name = tagging.normalize_tag(raw)
        if not name or name in existing:
            continue
        tag = db.execute(
            select(Tag).where(Tag.user_id == shot.user_id, Tag.name == name)
        ).scalar_one_or_none()
        if tag is None:
            tag = Tag(user_id=shot.user_id, name=name, auto=auto)
            db.add(tag)
            db.flush()
        shot.tags.append(tag)
        existing.add(name)


def cleanup_orphan_tags(db, user_id: int) -> int:
    """Delete the user's tags that are no longer attached to any screenshot.
    Caller is responsible for committing."""
    orphans = (
        db.execute(
            select(Tag).where(Tag.user_id == user_id, ~Tag.screenshots.any())
        )
        .scalars()
        .all()
    )
    for tag in orphans:
        db.delete(tag)
    return len(orphans)


def purge_old_trash(days: int = 30) -> int:
    """Permanently remove screenshots that have been in Trash longer than `days`."""
    cutoff = utcnow() - timedelta(days=days)
    db = SessionLocal()
    try:
        rows = (
            db.execute(
                select(Screenshot).where(
                    Screenshot.deleted_at.isnot(None), Screenshot.deleted_at < cutoff
                )
            )
            .scalars()
            .all()
        )
        affected_users = {s.user_id for s in rows}
        for shot in rows:
            remove_relpath(shot.storage_relpath)
            remove_relpath(shot.thumb_relpath)
            db.delete(shot)
        if rows:
            db.flush()
            for uid in affected_users:
                cleanup_orphan_tags(db, uid)
        db.commit()
        return len(rows)
    finally:
        db.close()


def requeue_stuck() -> int:
    """On startup, re-enqueue rows orphaned in 'processing' by a prior crash."""
    db = SessionLocal()
    try:
        stuck = (
            db.execute(
                select(Screenshot.id).where(
                    Screenshot.ocr_status == STATUS_PROCESSING
                )
            )
            .scalars()
            .all()
        )
        for sid in stuck:
            enqueue(sid)
        return len(stuck)
    finally:
        db.close()


def shutdown() -> None:
    _executor.shutdown(wait=False, cancel_futures=True)
