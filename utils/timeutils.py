"""Datetime helpers shared across models, services, and templates."""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_aware(dt: datetime) -> datetime:
    """Treat naive datetimes (e.g. from SQLite) as UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def humanize(dt: datetime) -> str:
    """Compact relative label, e.g. 'just now', '3h ago', 'Apr 2'."""
    dt = as_aware(dt)
    now = utcnow()
    delta = now - dt
    secs = delta.total_seconds()
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    if secs < 7 * 86400:
        return f"{int(secs // 86400)}d ago"
    if dt.year == now.year:
        return f"{dt.strftime('%b')} {dt.day}"
    return f"{dt.strftime('%b')} {dt.day}, {dt.year}"
