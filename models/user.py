"""User account model."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from utils.timeutils import utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120))
    avatar_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    screenshots = relationship(
        "Screenshot",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    tags = relationship(
        "Tag",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    saved_searches = relationship(
        "SavedSearch",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.id} {self.email}>"
