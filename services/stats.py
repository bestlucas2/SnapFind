"""Dashboard statistics — all scoped to the current user."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from models import (
    STATUS_FAILED,
    STATUS_INDEXED,
    STATUS_PROCESSING,
    Screenshot,
    Tag,
)
from utils.timeutils import as_aware, utcnow


def _count(db: Session, *conditions) -> int:
    return db.scalar(select(func.count(Screenshot.id)).where(*conditions)) or 0


def dashboard_stats(db: Session, user) -> dict:
    # All stats exclude soft-deleted (Trash) screenshots.
    uid = and_(Screenshot.user_id == user.id, Screenshot.deleted_at.is_(None))

    total = _count(db, uid, Screenshot.archived.is_(False))
    total_all = _count(db, uid)
    archived = _count(db, uid, Screenshot.archived.is_(True))
    favorites = _count(db, uid, Screenshot.favorite.is_(True), Screenshot.archived.is_(False))
    indexed = _count(db, uid, Screenshot.ocr_status == STATUS_INDEXED)
    processing = _count(db, uid, Screenshot.ocr_status == STATUS_PROCESSING)
    failed = _count(db, uid, Screenshot.ocr_status == STATUS_FAILED)

    storage_bytes = (
        db.scalar(
            select(func.coalesce(func.sum(Screenshot.file_size), 0)).where(uid)
        )
        or 0
    )

    ocr_rate = round((indexed / total_all) * 100) if total_all else 0

    categories_count = (
        db.scalar(
            select(func.count(func.distinct(Screenshot.category))).where(uid)
        )
        or 0
    )
    tags_count = db.scalar(
        select(func.count(Tag.id)).where(
            Tag.user_id == user.id,
            Tag.screenshots.any(Screenshot.deleted_at.is_(None)),
        )
    ) or 0

    # Top categories (non-archived).
    cat_rows = db.execute(
        select(Screenshot.category, func.count(Screenshot.id))
        .where(uid, Screenshot.archived.is_(False))
        .group_by(Screenshot.category)
        .order_by(func.count(Screenshot.id).desc())
    ).all()
    categories = [{"name": name, "count": cnt} for name, cnt in cat_rows]

    # Upload trend over the last 14 days, bucketed in Python for DB portability.
    span_days = 14
    today = utcnow().date()
    start = today - timedelta(days=span_days - 1)
    created_rows = db.execute(
        select(Screenshot.created_at).where(uid, Screenshot.archived.is_(False))
    ).scalars().all()
    buckets = {start + timedelta(days=i): 0 for i in range(span_days)}
    for created in created_rows:
        d = as_aware(created).date()
        if d in buckets:
            buckets[d] += 1
    trend = [
        {"label": d.strftime("%b %d"), "date": d.isoformat(), "count": c}
        for d, c in sorted(buckets.items())
    ]

    return {
        "total": total,
        "total_all": total_all,
        "archived": archived,
        "favorites": favorites,
        "indexed": indexed,
        "processing": processing,
        "failed": failed,
        "ocr_rate": ocr_rate,
        "storage_bytes": int(storage_bytes),
        "categories_count": categories_count,
        "tags_count": tags_count,
        "categories": categories,
        "trend": trend,
    }
