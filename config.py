"""Application configuration loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "SnapFind"
    debug: bool = True
    secret_key: str = "dev-insecure-secret-change-me"

    # Zero-config default: a local SQLite file (no services to run). For the
    # full multi-user deployment, set DATABASE_URL to a postgresql+psycopg://…
    # URL — docker-compose.yml provisions a matching instance.
    database_url: str = "sqlite:///./snapfind.db"

    storage_dir: str = "uploads"
    max_upload_mb: int = 25
    allowed_extensions: set[str] = {".png", ".jpg", ".jpeg", ".webp"}

    ocr_workers: int = 3
    tesseract_cmd: str | None = None

    # External services (optional — leave unset to disable).
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None
    anthropic_api_key: str | None = None

    @property
    def storage_path(self) -> Path:
        p = (BASE_DIR / self.storage_dir).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
