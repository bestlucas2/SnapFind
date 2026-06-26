"""HTMX partial endpoints for live, refresh-free search & filtering."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from auth import require_user
from database import get_db
from models import User
from services.search import search_screenshots, search_snippets
from templating import base_context, templates

router = APIRouter()


@router.get("/partials/screenshots")
def screenshots_partial(
    request: Request,
    q: str = "",
    view: str = "all",
    collection_id: int | None = None,
    tag: str | None = None,
    category: str | None = None,
    period: str | None = None,
    sort: str = "newest",
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    shots = search_screenshots(
        db, user, q=q, view=view, collection_id=collection_id,
        tag=tag, category=category, period=period, sort=sort,
    )
    ctx = base_context(
        request, user, db,
        screenshots=shots, snippets=search_snippets(shots, q), view=view, q=q,
        active_tag=tag, active_category=category,
    )
    return templates.TemplateResponse("partials/_grid.html", ctx)


@router.get("/partials/sidebar-categories")
def sidebar_categories_partial(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    return templates.TemplateResponse(
        "partials/_sidebar_categories.html", base_context(request, user, db)
    )
