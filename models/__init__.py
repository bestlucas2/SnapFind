"""Model package — import order registers all mappers on the metadata."""
from database import Base
from models.associations import screenshot_tags
from models.screenshot import (
    CATEGORIES,
    MAX_TAGS,
    STATUS_FAILED,
    STATUS_INDEXED,
    STATUS_PROCESSING,
    Screenshot,
)
from models.saved_search import SavedSearch
from models.tag import Tag
from models.user import User

__all__ = [
    "Base",
    "User",
    "Tag",
    "Screenshot",
    "SavedSearch",
    "screenshot_tags",
    "CATEGORIES",
    "MAX_TAGS",
    "STATUS_PROCESSING",
    "STATUS_INDEXED",
    "STATUS_FAILED",
]
