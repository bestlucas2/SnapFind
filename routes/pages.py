"""Top-level pages: landing, grid, timeline, dashboard, viewer."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_optional_user, get_owned_collection, require_user
from database import get_db
from models import Collection, User
from services.search import search_screenshots, search_snippets
from services.stats import dashboard_stats
from templating import base_context, templates
from utils.time_groups import group_by_period

router = APIRouter()


@router.get("/")
def landing(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    return templates.TemplateResponse(
        "landing.html", base_context(request, user, db if user else None)
    )


@router.get("/app")
def app_grid(
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
    active_collection = (
        get_owned_collection(collection_id, user, db) if collection_id else None
    )
    titles = {
        "all": "All Screenshots",
        "favorites": "Favorites",
        "recent": "Recent",
        "archive": "Archive",
        "trash": "Trash",
    }
    page_title = titles.get(view, "All Screenshots")
    if active_collection:
        page_title = active_collection.name
    elif tag:
        page_title = f"#{tag}"
    elif category:
        page_title = category

    ctx = base_context(
        request, user, db,
        screenshots=shots,
        snippets=search_snippets(shots, q),
        view=view, q=q, sort=sort, period=period,
        active_collection=active_collection,
        active_tag=tag, active_category=category,
        page_title=page_title,
    )
    return templates.TemplateResponse("pages/grid.html", ctx)


@router.get("/timeline")
def timeline(
    request: Request,
    q: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    shots = search_screenshots(db, user, q=q, view="all", sort="newest")
    groups = group_by_period(shots)
    ctx = base_context(
        request, user, db, groups=groups, q=q, total=len(shots),
        page_title="Timeline",
    )
    return templates.TemplateResponse("pages/timeline.html", ctx)


@router.get("/dashboard")
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    stats = dashboard_stats(db, user)
    ctx = base_context(request, user, db, stats=stats, page_title="Dashboard")
    return templates.TemplateResponse("pages/dashboard.html", ctx)


@router.get("/screenshot/{screenshot_id}")
def viewer(
    request: Request,
    screenshot_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    # Ownership enforced via the single chokepoint helper.
    from auth import get_owned_screenshot

    shot = get_owned_screenshot(screenshot_id, user, db)
    all_collections = (
        db.execute(
            select(Collection)
            .where(Collection.user_id == user.id)
            .order_by(Collection.name)
        )
        .scalars()
        .all()
    )
    ctx = base_context(
        request, user, db, shot=shot, all_collections=all_collections,
        page_title=shot.filename,
    )
    return templates.TemplateResponse("pages/viewer.html", ctx)
