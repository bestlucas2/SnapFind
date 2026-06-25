"""Group screenshots into timeline buckets: Today, Yesterday, This Week, months."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta

from utils.timeutils import as_aware, utcnow


def group_by_period(screenshots: Iterable) -> list[tuple[str, list]]:
    """Return ordered (label, items) groups, newest first.

    Items are assumed already sorted by created_at descending.
    """
    now = utcnow()
    today = now.date()
    yesterday = today - timedelta(days=1)
    week_start = today - timedelta(days=today.weekday())  # Monday

    groups: dict[str, list] = {}
    order: list[str] = []

    def bucket(label: str, item) -> None:
        if label not in groups:
            groups[label] = []
            order.append(label)
        groups[label].append(item)

    for shot in screenshots:
        created = as_aware(shot.created_at)
        d = created.date()
        if d == today:
            label = "Today"
        elif d == yesterday:
            label = "Yesterday"
        elif d >= week_start:
            label = "This Week"
        elif d.year == today.year:
            label = created.strftime("%B")
        else:
            label = created.strftime("%B %Y")
        bucket(label, shot)

    return [(label, groups[label]) for label in order]
