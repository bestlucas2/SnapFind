"""Tag model — user-scoped, many-to-many with screenshots."""
from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.associations import screenshot_tags


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_tag_user_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80), index=True)
    auto: Mapped[bool] = mapped_column(default=False)  # generated vs manual

    user = relationship("User", back_populates="tags")
    screenshots = relationship(
        "Screenshot",
        secondary=screenshot_tags,
        back_populates="tags",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Tag {self.id} {self.name!r}>"
