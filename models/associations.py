"""Association tables for many-to-many relationships."""
from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Table

from database import Base

# Screenshot <-> Tag (many-to-many). Tags themselves are scoped per-user, so
# this join inherits that isolation through the rows it links.
screenshot_tags = Table(
    "screenshot_tags",
    Base.metadata,
    Column(
        "screenshot_id",
        ForeignKey("screenshots.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)
