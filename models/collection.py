"""Collection (folder) model — user-scoped."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from utils.timeutils import utcnow


class Collection(Base):
    __tablename__ = "collections"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_collection_user_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    icon: Mapped[str] = mapped_column(String(40), default="folder")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    user = relationship("User", back_populates="collections")
    screenshots = relationship("Screenshot", back_populates="collection")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Collection {self.id} {self.name!r}>"
