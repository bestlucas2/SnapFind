"""Screenshot model — the core entity, user-scoped."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.associations import screenshot_tags
from utils.timeutils import utcnow

# OCR lifecycle states surfaced as status badges in the UI.
STATUS_PROCESSING = "processing"
STATUS_INDEXED = "indexed"
STATUS_FAILED = "failed"

# Maximum number of tags allowed per screenshot.
MAX_TAGS = 3

# Auto-categorisation buckets.
CATEGORIES = [
    "School",
    "Chats",
    "Receipts",
    "Code",
    "Shopping",
    "Photos",
    "Miscellaneous",
]


class Screenshot(Base):
    __tablename__ = "screenshots"
    __table_args__ = (
        # Duplicate detection is scoped per-user: two different people
        # uploading the same image are not duplicates of each other.
        Index("ix_screenshot_user_hash", "user_id", "image_hash"),
        Index("ix_screenshot_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # Display + storage
    filename: Mapped[str] = mapped_column(String(255))           # editable label
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255))    # on-disk name
    thumb_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str] = mapped_column(String(80))
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Duplicate detection
    image_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # OCR
    ocr_text: Mapped[str] = mapped_column(Text, default="")
    ocr_status: Mapped[str] = mapped_column(String(20), default=STATUS_PROCESSING)
    ocr_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Organisation
    category: Mapped[str] = mapped_column(String(40), default="Miscellaneous")
    notes: Mapped[str] = mapped_column(Text, default="")
    favorite: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    # Soft delete: non-null means the screenshot is in the Trash.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    user = relationship("User", back_populates="screenshots")
    tags = relationship(
        "Tag",
        secondary=screenshot_tags,
        back_populates="screenshots",
        order_by="Tag.name",
    )

    # --- Convenience helpers used by templates / serialisers ---
    @property
    def storage_relpath(self) -> str:
        """Path relative to the storage root: <user_id>/<stored_filename>."""
        return f"{self.user_id}/{self.stored_filename}"

    @property
    def thumb_relpath(self) -> str | None:
        if not self.thumb_filename:
            return None
        return f"{self.user_id}/{self.thumb_filename}"

    @property
    def size_human(self) -> str:
        size = float(self.file_size or 0)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "original_filename": self.original_filename,
            "content_type": self.content_type,
            "file_size": self.file_size,
            "width": self.width,
            "height": self.height,
            "image_hash": self.image_hash,
            "ocr_text": self.ocr_text,
            "ocr_status": self.ocr_status,
            "category": self.category,
            "notes": self.notes,
            "favorite": self.favorite,
            "archived": self.archived,
            "tags": [t.name for t in self.tags],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Screenshot {self.id} {self.filename!r} {self.ocr_status}>"
