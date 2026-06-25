"""Collection CRUD. Drag-and-drop assignment reuses /screenshot/{id}/move."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_owned_collection, require_user, verify_csrf
from database import get_db
from models import Collection, User
from templating import base_context, templates

router = APIRouter()


def _sidebar_collections(request, user, db):
    return templates.TemplateResponse(
        "partials/_sidebar_collections.html", base_context(request, user, db)
    )


@router.post("/collections", dependencies=[Depends(verify_csrf)])
def create_collection(
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    clean = name.strip()[:120]
    if clean:
        exists = db.execute(
            select(Collection).where(
                Collection.user_id == user.id, Collection.name == clean
            )
        ).scalar_one_or_none()
        if exists is None:
            db.add(Collection(user_id=user.id, name=clean))
            db.commit()
    return _sidebar_collections(request, user, db)


@router.post("/collections/{collection_id}/rename", dependencies=[Depends(verify_csrf)])
def rename_collection(
    request: Request,
    collection_id: int,
    name: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    collection = get_owned_collection(collection_id, user, db)
    clean = name.strip()[:120]
    if clean:
        collection.name = clean
        db.commit()
    return _sidebar_collections(request, user, db)


@router.delete("/collections/{collection_id}", dependencies=[Depends(verify_csrf)])
def delete_collection(
    request: Request,
    collection_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    collection = get_owned_collection(collection_id, user, db)
    # Screenshots keep existing; their collection_id is set NULL by the FK.
    db.delete(collection)
    db.commit()
    response = _sidebar_collections(request, user, db)
    response.headers["HX-Trigger"] = "refresh-grid"
    return response
