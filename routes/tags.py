"""Tag management: delete, rename, merge, and a management page."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from auth import get_owned_tag, require_user, verify_csrf
from database import get_db
from models import MAX_TAGS, Screenshot, Tag, User, screenshot_tags
from services.tagging import normalize_tag
from templating import base_context, templates

router = APIRouter()


def _manage_context(request: Request, user: User, db: Session) -> dict:
    tags = (
        db.execute(
            select(Tag).where(Tag.user_id == user.id).order_by(func.lower(Tag.name))
        )
        .scalars()
        .all()
    )
    counts = dict(
        db.execute(
            select(screenshot_tags.c.tag_id, func.count())
            .join(Screenshot, Screenshot.id == screenshot_tags.c.screenshot_id)
            .where(Screenshot.user_id == user.id, Screenshot.deleted_at.is_(None))
            .group_by(screenshot_tags.c.tag_id)
        ).all()
    )
    return base_context(request, user, db, manage_tags=tags, tag_counts=counts)


def _manage_list(request: Request, user: User, db: Session):
    return templates.TemplateResponse(
        "partials/_tag_manage_list.html", _manage_context(request, user, db)
    )


def _merge_into(db: Session, source: Tag, target: Tag) -> None:
    """Reassign all of `source`'s screenshots to `target` (respecting MAX_TAGS),
    then delete the now-empty source tag."""
    for shot in list(source.screenshots):
        shot.tags.remove(source)
        if target not in shot.tags and len(shot.tags) < MAX_TAGS:
            shot.tags.append(target)
    db.delete(source)


@router.get("/tags/manage")
def manage_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    return templates.TemplateResponse(
        "pages/tags_manage.html", _manage_context(request, user, db)
    )


@router.post("/tags/{tag_id}/rename", dependencies=[Depends(verify_csrf)])
def rename_tag(
    request: Request,
    tag_id: int,
    name: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    tag = get_owned_tag(tag_id, user, db)
    new = normalize_tag(name)
    if new and new != tag.name:
        existing = db.execute(
            select(Tag).where(
                Tag.user_id == user.id, Tag.name == new, Tag.id != tag.id
            )
        ).scalar_one_or_none()
        if existing is not None:
            # Renaming onto an existing tag == merging into it.
            _merge_into(db, tag, existing)
        else:
            tag.name = new
        db.commit()
    return _manage_list(request, user, db)


@router.post("/tags/merge", dependencies=[Depends(verify_csrf)])
def merge_tags(
    request: Request,
    source_id: int = Form(...),
    target_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if source_id != target_id:
        source = get_owned_tag(source_id, user, db)
        target = get_owned_tag(target_id, user, db)
        _merge_into(db, source, target)
        db.commit()
    return _manage_list(request, user, db)


@router.delete("/tags/{tag_id}", dependencies=[Depends(verify_csrf)])
def delete_tag(
    request: Request,
    tag_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    tag = get_owned_tag(tag_id, user, db)
    db.delete(tag)
    db.commit()
    response = templates.TemplateResponse(
        "partials/_sidebar_tags.html", base_context(request, user, db)
    )
    response.headers["HX-Trigger"] = "refresh-grid"
    return response
