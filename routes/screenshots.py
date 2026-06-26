"""Per-screenshot actions + image serving. All go through get_owned_screenshot."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import (
    get_owned_screenshot,
    require_user,
    verify_csrf,
)
from database import get_db
from models import MAX_TAGS, STATUS_PROCESSING, Screenshot, Tag, User
from services import processing
from services.search import search_screenshots
from templating import base_context, templates
from utils.files import get_bytes, remove_relpath
from utils.timeutils import utcnow

router = APIRouter()


def _card(request, user, db, shot):
    return templates.TemplateResponse(
        "partials/_card.html", base_context(request, user, db, shot=shot)
    )


def _tags_partial(request, user, db, shot):
    return templates.TemplateResponse(
        "partials/_tags.html", base_context(request, user, db, shot=shot)
    )


# --------------------------------------------------------------------------- #
# Status badge (polled by the grid while OCR runs)
# --------------------------------------------------------------------------- #
@router.get("/status/{screenshot_id}")
def status_badge(
    request: Request,
    screenshot_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    shot = get_owned_screenshot(screenshot_id, user, db)
    return templates.TemplateResponse(
        "partials/_status_badge.html", base_context(request, user, db, shot=shot)
    )


# --------------------------------------------------------------------------- #
# Image serving (ownership-checked — never via a public static mount)
# --------------------------------------------------------------------------- #
@router.get("/screenshot/{screenshot_id}/neighbor")
def neighbor(
    screenshot_id: int,
    dir: str = "next",
    q: str = "",
    view: str = "all",
    tag: str | None = None,
    category: str | None = None,
    period: str | None = None,
    sort: str = "newest",
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Return the id of the previous/next screenshot within the active filter."""
    shots = search_screenshots(
        db, user, q=q, view=view,
        tag=tag, category=category, period=period, sort=sort,
    )
    ids = [s.id for s in shots]
    if screenshot_id not in ids:
        return JSONResponse({"id": None})
    i = ids.index(screenshot_id)
    j = i - 1 if dir == "prev" else i + 1
    return JSONResponse({"id": ids[j] if 0 <= j < len(ids) else None})


@router.post("/screenshot/{screenshot_id}/retry", dependencies=[Depends(verify_csrf)])
def retry_ocr(
    request: Request,
    screenshot_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    """Re-run OCR in place via the existing pipeline. Works on any status."""
    shot = get_owned_screenshot(screenshot_id, user, db)
    shot.ocr_status = STATUS_PROCESSING
    shot.ocr_error = None
    db.commit()
    processing.enqueue(shot.id)
    return templates.TemplateResponse(
        "partials/_status_badge.html", base_context(request, user, db, shot=shot)
    )


@router.get("/screenshot/{screenshot_id}/raw")
def raw_image(
    screenshot_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    shot = get_owned_screenshot(screenshot_id, user, db)
    data = get_bytes(shot.storage_relpath)
    if data is None:
        return Response(status_code=404)
    return Response(data, media_type=shot.content_type)


@router.get("/screenshot/{screenshot_id}/thumb")
def thumb_image(
    screenshot_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    shot = get_owned_screenshot(screenshot_id, user, db)
    data = get_bytes(shot.thumb_relpath) if shot.thumb_relpath else None
    media = "image/jpeg"
    if data is None:
        data = get_bytes(shot.storage_relpath)
        media = shot.content_type
    if data is None:
        return Response(status_code=404)
    return Response(data, media_type=media)


@router.get("/screenshot/{screenshot_id}/download")
def download_image(
    screenshot_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    shot = get_owned_screenshot(screenshot_id, user, db)
    data = get_bytes(shot.storage_relpath)
    if data is None:
        return Response(status_code=404)
    return Response(
        data,
        media_type=shot.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{shot.original_filename}"'
        },
    )


# --------------------------------------------------------------------------- #
# Mutations
# --------------------------------------------------------------------------- #
@router.post("/screenshot/{screenshot_id}/favorite", dependencies=[Depends(verify_csrf)])
def toggle_favorite(
    request: Request,
    screenshot_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    shot = get_owned_screenshot(screenshot_id, user, db)
    shot.favorite = not shot.favorite
    db.commit()
    return templates.TemplateResponse(
        "partials/_favorite_button.html", base_context(request, user, db, shot=shot)
    )


@router.post("/screenshot/{screenshot_id}/archive", dependencies=[Depends(verify_csrf)])
def toggle_archive(
    request: Request,
    screenshot_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    shot = get_owned_screenshot(screenshot_id, user, db)
    shot.archived = not shot.archived
    db.commit()
    response = Response(status_code=200)
    response.headers["HX-Trigger"] = "refresh-grid"
    return response


@router.post("/screenshot/{screenshot_id}/rename", dependencies=[Depends(verify_csrf)])
def rename(
    request: Request,
    screenshot_id: int,
    filename: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    shot = get_owned_screenshot(screenshot_id, user, db)
    new_name = filename.strip()[:255]
    if new_name:
        shot.filename = new_name
        db.commit()
    return templates.TemplateResponse(
        "partials/_title.html", base_context(request, user, db, shot=shot)
    )


@router.post("/screenshot/{screenshot_id}/notes", dependencies=[Depends(verify_csrf)])
def update_notes(
    request: Request,
    screenshot_id: int,
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    shot = get_owned_screenshot(screenshot_id, user, db)
    shot.notes = notes.strip()
    db.commit()
    return Response(
        '<span class="text-xs text-emerald-500">Saved</span>', media_type="text/html"
    )


@router.post("/screenshot/{screenshot_id}/category", dependencies=[Depends(verify_csrf)])
def update_category(
    screenshot_id: int,
    category: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    shot = get_owned_screenshot(screenshot_id, user, db)
    shot.category = category.strip()[:40] or "Miscellaneous"
    db.commit()
    response = Response(status_code=200)
    response.headers["HX-Trigger"] = "refresh-grid"
    return response


@router.post("/screenshot/{screenshot_id}/tags/add", dependencies=[Depends(verify_csrf)])
def add_tag(
    request: Request,
    screenshot_id: int,
    tag: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    shot = get_owned_screenshot(screenshot_id, user, db)
    # attach_tags enforces the per-screenshot MAX_TAGS cap.
    processing.attach_tags(db, shot, [tag], auto=False)
    db.commit()
    return _tags_partial(request, user, db, shot)


@router.post(
    "/screenshot/{screenshot_id}/tags/{tag_id}/remove",
    dependencies=[Depends(verify_csrf)],
)
def remove_tag(
    request: Request,
    screenshot_id: int,
    tag_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    shot = get_owned_screenshot(screenshot_id, user, db)
    tag = next((t for t in shot.tags if t.id == tag_id), None)
    if tag is not None:
        shot.tags.remove(tag)
        db.flush()
        processing.cleanup_orphan_tags(db, user.id)  # drop the tag if now unused
        db.commit()
    return _tags_partial(request, user, db, shot)


@router.delete("/screenshot/{screenshot_id}", dependencies=[Depends(verify_csrf)])
def delete_screenshot(
    screenshot_id: int,
    redirect: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    shot = get_owned_screenshot(screenshot_id, user, db)
    if shot.deleted_at is None:
        shot.deleted_at = utcnow()  # soft delete -> Trash
        db.commit()
    response = Response(status_code=200)
    if redirect:
        response.headers["HX-Redirect"] = f"{redirect}?undo={shot.id}"
    else:
        response.headers["HX-Trigger"] = json.dumps(
            {"refresh-grid": True, "snap-undo": {"ids": [shot.id]}}
        )
    return response


@router.post("/screenshot/{screenshot_id}/restore", dependencies=[Depends(verify_csrf)])
def restore_screenshot(
    screenshot_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    shot = get_owned_screenshot(screenshot_id, user, db)
    shot.deleted_at = None
    db.commit()
    response = Response(status_code=200)
    response.headers["HX-Trigger"] = "refresh-grid"
    return response


@router.delete(
    "/screenshot/{screenshot_id}/permanent", dependencies=[Depends(verify_csrf)]
)
def permanent_delete(
    screenshot_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    shot = get_owned_screenshot(screenshot_id, user, db)
    remove_relpath(shot.storage_relpath)
    remove_relpath(shot.thumb_relpath)
    db.delete(shot)
    db.flush()
    processing.cleanup_orphan_tags(db, user.id)  # drop tags left unused
    db.commit()
    response = Response(status_code=200)
    response.headers["HX-Trigger"] = "refresh-grid"
    return response
