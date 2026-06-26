"""Export the current view as ZIP, CSV, or JSON."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from auth import require_user
from database import get_db
from models import User
from services import export as export_service
from services.search import search_screenshots

router = APIRouter()

_MEDIA = {
    "zip": "application/zip",
    "csv": "text/csv",
    "json": "application/json",
}


@router.get("/export")
def export_screenshots(
    format: str = "json",
    q: str = "",
    view: str = "all",
    tag: str | None = None,
    category: str | None = None,
    period: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    fmt = format.lower()
    if fmt not in _MEDIA:
        fmt = "json"

    shots = search_screenshots(
        db, user, q=q, view=view,
        tag=tag, category=category, period=period,
    )

    if fmt == "zip":
        body = export_service.to_zip(shots)
    elif fmt == "csv":
        body = export_service.to_csv(shots)
    else:
        body = export_service.to_json(shots)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"snapfind-export-{stamp}.{fmt}"
    return Response(
        content=body,
        media_type=_MEDIA[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
