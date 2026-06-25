"""Saved searches / smart collections — named, re-runnable queries (per-user)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import require_user, verify_csrf
from database import get_db
from models import SavedSearch, User
from templating import base_context, templates

router = APIRouter()


def _saved_partial(request, user, db):
    return templates.TemplateResponse(
        "partials/_sidebar_saved.html", base_context(request, user, db)
    )


@router.post("/saved-searches", dependencies=[Depends(verify_csrf)])
def create_saved(
    request: Request,
    name: str = Form(...),
    query: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    clean = name.strip()[:120]
    if clean:
        db.add(SavedSearch(user_id=user.id, name=clean, query=query.strip()[:500]))
        db.commit()
    return _saved_partial(request, user, db)


@router.delete("/saved-searches/{saved_id}", dependencies=[Depends(verify_csrf)])
def delete_saved(
    request: Request,
    saved_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    obj = db.execute(
        select(SavedSearch).where(
            SavedSearch.id == saved_id, SavedSearch.user_id == user.id
        )
    ).scalar_one_or_none()
    if obj is not None:
        db.delete(obj)
        db.commit()
    return _saved_partial(request, user, db)
