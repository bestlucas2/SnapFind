"""Jinja2 setup and the shared template context (nav + sidebar data)."""
from __future__ import annotations

import time

from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from auth import ensure_csrf_token
from config import BASE_DIR, settings
from models import CATEGORIES, MAX_TAGS, Collection, SavedSearch, Screenshot, Tag
from utils.linkify import linkify_ocr
from utils.timeutils import humanize

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["humanize"] = humanize
templates.env.globals["app_name"] = settings.app_name
templates.env.globals["categories"] = CATEGORIES
templates.env.globals["max_tags"] = MAX_TAGS
templates.env.globals["linkify_ocr"] = linkify_ocr
# Cache-busting token for static assets — changes on each server start so
# browsers always fetch the latest CSS/JS instead of a stale cached copy.
templates.env.globals["asset_version"] = str(int(time.time()))


# Starlette >= 1.0 requires TemplateResponse(request, name, context); older code
# (and this project) calls TemplateResponse(name, context-with-request). This
# shim accepts the legacy form so every call site stays simple.
_orig_template_response = templates.TemplateResponse


def _compat_template_response(*args, **kwargs):
    if args and isinstance(args[0], str):
        name = args[0]
        context = args[1] if len(args) > 1 else kwargs.pop("context", {})
        request = (context or {}).get("request")
        return _orig_template_response(request, name, context, *args[2:], **kwargs)
    return _orig_template_response(*args, **kwargs)


templates.TemplateResponse = _compat_template_response


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def sidebar_context(db: Session, user) -> dict:
    uid = Screenshot.user_id == user.id
    live = Screenshot.deleted_at.is_(None)  # not in Trash
    all_count = db.scalar(
        select(func.count(Screenshot.id)).where(uid, live, Screenshot.archived.is_(False))
    ) or 0
    fav_count = db.scalar(
        select(func.count(Screenshot.id)).where(
            uid, live, Screenshot.favorite.is_(True), Screenshot.archived.is_(False)
        )
    ) or 0
    archive_count = db.scalar(
        select(func.count(Screenshot.id)).where(uid, live, Screenshot.archived.is_(True))
    ) or 0
    trash_count = db.scalar(
        select(func.count(Screenshot.id)).where(uid, Screenshot.deleted_at.isnot(None))
    ) or 0

    coll_rows = db.execute(
        select(Collection, func.count(Screenshot.id))
        .outerjoin(
            Screenshot,
            (Screenshot.collection_id == Collection.id)
            & (Screenshot.archived.is_(False))
            & (Screenshot.deleted_at.is_(None)),
        )
        .where(Collection.user_id == user.id)
        .group_by(Collection.id)
        .order_by(func.lower(Collection.name))
    ).all()
    collections = [{"obj": c, "count": n} for c, n in coll_rows]

    # Only surface tags attached to at least one live (non-trashed) screenshot.
    used = Tag.screenshots.any(Screenshot.deleted_at.is_(None))
    tags = (
        db.execute(
            select(Tag)
            .where(Tag.user_id == user.id, used)
            .order_by(func.lower(Tag.name))
            .limit(50)
        )
        .scalars()
        .all()
    )
    tags_total = db.scalar(
        select(func.count(Tag.id)).where(Tag.user_id == user.id, used)
    ) or 0
    all_tag_names = list(
        db.execute(
            select(Tag.name)
            .where(Tag.user_id == user.id, used)
            .order_by(func.lower(Tag.name))
        ).scalars()
    )
    used_categories = db.execute(
        select(Screenshot.category)
        .where(Screenshot.user_id == user.id, Screenshot.category.isnot(None))
        .distinct()
    ).scalars()
    all_categories = sorted({*CATEGORIES, *(c for c in used_categories if c)})

    # Categories actually in use (live, non-archived), with counts, for the sidebar.
    cat_count_rows = db.execute(
        select(Screenshot.category, func.count(Screenshot.id))
        .where(
            Screenshot.user_id == user.id,
            live,
            Screenshot.archived.is_(False),
            Screenshot.category.isnot(None),
        )
        .group_by(Screenshot.category)
        .order_by(func.lower(Screenshot.category))
    ).all()
    sidebar_categories = [{"name": c, "count": n} for c, n in cat_count_rows if c]

    saved_searches = (
        db.execute(
            select(SavedSearch)
            .where(SavedSearch.user_id == user.id)
            .order_by(SavedSearch.created_at.desc())
        )
        .scalars()
        .all()
    )

    return {
        "nav_counts": {
            "all": all_count,
            "favorites": fav_count,
            "archive": archive_count,
            "trash": trash_count,
        },
        "sidebar_collections": collections,
        "sidebar_categories": sidebar_categories,
        "sidebar_tags": tags,
        "tags_total": tags_total,
        "all_tag_names": all_tag_names,
        "all_categories": all_categories,
        "saved_searches": saved_searches,
    }


def base_context(request: Request, user, db: Session | None = None, **extra) -> dict:
    ctx = {
        "request": request,
        "current_user": user,
        "csrf_token": ensure_csrf_token(request),
        "settings": settings,
    }
    if user is not None and db is not None:
        ctx.update(sidebar_context(db, user))
    ctx.update(extra)
    return ctx
