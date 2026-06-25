"""Batch actions on multiple screenshots.

Every endpoint takes a comma-separated `ids` list, filters it to rows owned by
the current user (silently dropping any that aren't), and applies the change in
a single transaction by reusing the same per-item logic as the single endpoints.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_owned_collection, require_user, verify_csrf
from database import get_db
from models import STATUS_PROCESSING, Screenshot, User
from services import export as export_service
from services import processing
from utils.files import remove_relpath
from utils.timeutils import utcnow

router = APIRouter()

_TRUE = {"1", "true", "yes", "on"}


def _parse_ids(raw: str) -> list[int]:
    out: list[int] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


def _owned(db: Session, user: User, ids: list[int], scope: str = "active") -> list[Screenshot]:
    if not ids:
        return []
    stmt = select(Screenshot).where(
        Screenshot.id.in_(ids), Screenshot.user_id == user.id
    )
    if scope == "active":
        stmt = stmt.where(Screenshot.deleted_at.is_(None))
    elif scope == "trash":
        stmt = stmt.where(Screenshot.deleted_at.isnot(None))
    return list(db.execute(stmt).scalars().all())


@router.post("/bulk/tag", dependencies=[Depends(verify_csrf)])
def bulk_tag(
    ids: str = Form(""),
    tag: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    for shot in _owned(db, user, _parse_ids(ids)):
        processing.attach_tags(db, shot, [tag], auto=False)  # enforces MAX_TAGS
    db.commit()
    return Response(status_code=200)


@router.post("/bulk/move", dependencies=[Depends(verify_csrf)])
def bulk_move(
    ids: str = Form(""),
    collection_id: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    target = None
    if collection_id and collection_id != "0":
        target = get_owned_collection(int(collection_id), user, db)
    for shot in _owned(db, user, _parse_ids(ids)):
        shot.collection_id = target.id if target else None
    db.commit()
    return Response(status_code=200)


@router.post("/bulk/favorite", dependencies=[Depends(verify_csrf)])
def bulk_favorite(
    ids: str = Form(""),
    favorite: str = Form("1"),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    value = favorite.lower() in _TRUE
    for shot in _owned(db, user, _parse_ids(ids)):
        shot.favorite = value
    db.commit()
    return Response(status_code=200)


@router.post("/bulk/archive", dependencies=[Depends(verify_csrf)])
def bulk_archive(
    ids: str = Form(""),
    archived: str = Form("1"),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    value = archived.lower() in _TRUE
    for shot in _owned(db, user, _parse_ids(ids)):
        shot.archived = value
    db.commit()
    return Response(status_code=200)


@router.post("/bulk/delete", dependencies=[Depends(verify_csrf)])
def bulk_delete(
    ids: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    now = utcnow()
    affected: list[int] = []
    for shot in _owned(db, user, _parse_ids(ids)):
        if shot.deleted_at is None:
            shot.deleted_at = now
        affected.append(shot.id)
    db.commit()
    return JSONResponse({"ids": affected})


@router.post("/bulk/retry", dependencies=[Depends(verify_csrf)])
def bulk_retry(
    ids: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    shots = _owned(db, user, _parse_ids(ids))
    for shot in shots:
        shot.ocr_status = STATUS_PROCESSING
        shot.ocr_error = None
    db.commit()
    for shot in shots:
        processing.enqueue(shot.id)
    return Response(status_code=200)


@router.post("/bulk/restore", dependencies=[Depends(verify_csrf)])
def bulk_restore(
    ids: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    for shot in _owned(db, user, _parse_ids(ids), scope="trash"):
        shot.deleted_at = None
    db.commit()
    return Response(status_code=200)


@router.post("/bulk/permanent", dependencies=[Depends(verify_csrf)])
def bulk_permanent(
    ids: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    shots = _owned(db, user, _parse_ids(ids), scope="trash")
    for shot in shots:
        remove_relpath(shot.storage_relpath)
        remove_relpath(shot.thumb_relpath)
        db.delete(shot)
    if shots:
        db.flush()
        processing.cleanup_orphan_tags(db, user.id)
    db.commit()
    return Response(status_code=200)


_MEDIA = {"zip": "application/zip", "csv": "text/csv", "json": "application/json"}


@router.get("/bulk/export")
def bulk_export(
    ids: str = "",
    format: str = "zip",
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    fmt = format.lower()
    if fmt not in _MEDIA:
        fmt = "zip"
    shots = _owned(db, user, _parse_ids(ids))
    if fmt == "zip":
        body = export_service.to_zip(shots)
    elif fmt == "csv":
        body = export_service.to_csv(shots)
    else:
        body = export_service.to_json(shots)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Response(
        content=body,
        media_type=_MEDIA[fmt],
        headers={
            "Content-Disposition": f'attachment; filename="snapfind-selection-{stamp}.{fmt}"'
        },
    )
