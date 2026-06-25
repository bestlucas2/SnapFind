"""Screenshot search & filtering — merges free text, operators, and UI filters.

Full-text matching uses ILIKE across OCR text / filename / notes, which works
identically on Postgres and the SQLite fallback. (A Postgres tsvector + GIN
index is the natural next step if the corpus grows large.)
"""
from __future__ import annotations

import html
import re
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from models import Collection, Screenshot, Tag, screenshot_tags
from utils.search_parser import parse_query


def _day_start(d) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def search_screenshots(
    db: Session,
    user,
    *,
    q: str = "",
    view: str = "all",          # all | favorites | recent | archive
    collection_id: int | None = None,
    tag: str | None = None,
    category: str | None = None,
    period: str | None = None,  # today | week | month
    sort: str = "newest",       # newest | oldest | name | size
    limit: int | None = None,
) -> list[Screenshot]:
    pq = parse_query(q or "")

    stmt = (
        select(Screenshot)
        .where(Screenshot.user_id == user.id)
        .options(selectinload(Screenshot.tags), selectinload(Screenshot.collection))
    )

    # Trash shows only soft-deleted rows; every other view excludes them.
    if view == "trash":
        stmt = stmt.where(Screenshot.deleted_at.isnot(None))
    else:
        stmt = stmt.where(Screenshot.deleted_at.is_(None))
        # Archive: only the archive view shows archived items.
        if view == "archive":
            stmt = stmt.where(Screenshot.archived.is_(True))
        else:
            stmt = stmt.where(Screenshot.archived.is_(False))

    if view == "favorites":
        stmt = stmt.where(Screenshot.favorite.is_(True))
    if pq.favorite is not None:
        stmt = stmt.where(Screenshot.favorite.is_(pq.favorite))

    if collection_id:
        stmt = stmt.where(Screenshot.collection_id == collection_id)
    if pq.collection:
        stmt = stmt.where(
            Screenshot.collection_id.in_(
                select(Collection.id).where(
                    Collection.user_id == user.id,
                    func.lower(Collection.name) == pq.collection.lower(),
                )
            )
        )

    if category:
        stmt = stmt.where(Screenshot.category == category)

    # Tags (explicit filter + tag: operators); require ALL specified tags.
    tag_names = [t.lower() for t in pq.tags]
    if tag:
        tag_names.append(tag.lower())
    for tname in tag_names:
        sub = (
            select(screenshot_tags.c.screenshot_id)
            .join(Tag, Tag.id == screenshot_tags.c.tag_id)
            .where(Tag.user_id == user.id, func.lower(Tag.name) == tname)
        )
        stmt = stmt.where(Screenshot.id.in_(sub))

    # Date bounds: explicit period buttons + before:/after: operators.
    after = pq.after
    before = pq.before
    if period:
        today = datetime.now(timezone.utc).date()
        if period == "today":
            after = today
        elif period == "week":
            after = today - timedelta(days=7)
        elif period == "month":
            after = today - timedelta(days=30)
    if after:
        stmt = stmt.where(Screenshot.created_at >= _day_start(after))
    if before:
        stmt = stmt.where(Screenshot.created_at < _day_start(before) + timedelta(days=1))

    # Free text.
    if pq.text:
        like = f"%{pq.text}%"
        stmt = stmt.where(
            or_(
                Screenshot.ocr_text.ilike(like),
                Screenshot.filename.ilike(like),
                Screenshot.original_filename.ilike(like),
                Screenshot.notes.ilike(like),
            )
        )

    # Sort.
    if view == "recent":
        sort = "newest"
    if view == "trash":
        stmt = stmt.order_by(Screenshot.deleted_at.desc())
    elif sort == "oldest":
        stmt = stmt.order_by(Screenshot.created_at.asc())
    elif sort == "name":
        stmt = stmt.order_by(func.lower(Screenshot.filename).asc())
    elif sort == "size":
        stmt = stmt.order_by(Screenshot.file_size.desc())
    else:
        stmt = stmt.order_by(Screenshot.created_at.desc())

    if view == "recent" and limit is None:
        limit = 30
    if limit:
        stmt = stmt.limit(limit)

    return list(db.execute(stmt).scalars().unique().all())


_MARK_OPEN = "<mark class='bg-yellow-200 dark:bg-yellow-500/30 rounded px-0.5'>"
_MARK_CLOSE = "</mark>"


def search_snippets(screenshots, q: str, context: int = 55) -> dict[int, str]:
    """Return {id: safe-HTML snippet} for the free-text part of a query.

    Content is HTML-escaped first, then matched terms are wrapped in <mark>, so
    OCR text can never inject markup. Operator-only queries produce no snippets.
    """
    pq = parse_query(q or "")
    text = pq.text.strip()
    if not text:
        return {}
    terms = [t for t in re.split(r"\s+", text) if len(t) >= 2]
    if not terms:
        return {}
    pattern = re.compile("|".join(re.escape(t) for t in terms), re.IGNORECASE)

    out: dict[int, str] = {}
    for shot in screenshots:
        ocr = shot.ocr_text or ""
        m = pattern.search(ocr)
        if not m:
            continue
        start = max(0, m.start() - context)
        end = min(len(ocr), m.end() + context)
        window = ocr[start:end].replace("\n", " ")
        escaped = html.escape(window)
        # Re-match over the escaped window; plain word terms are unchanged by
        # escaping, so wrapping them in <mark> keeps the content safe.
        highlighted = pattern.sub(lambda mo: _MARK_OPEN + mo.group(0) + _MARK_CLOSE, escaped)
        prefix = "… " if start > 0 else ""
        suffix = " …" if end < len(ocr) else ""
        out[shot.id] = prefix + highlighted + suffix
    return out
