"""Database engine, session factory, and declarative base."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings

# SQLite needs a special flag for multi-threaded access (we touch the DB from
# OCR worker threads). Postgres needs no such argument.
_is_sqlite = settings.database_url.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

engine = create_engine(
    settings.database_url,
    echo=False,
    future=True,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_missing_columns() -> None:
    """Tiny additive migration: ALTER TABLE ADD COLUMN for any nullable column
    present in the models but missing from an existing table. Lets the schema
    evolve without dropping the dev database. (New tables are handled by
    create_all.)"""
    insp = inspect(engine)
    dialect = engine.dialect
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing or not col.nullable:
                continue
            coltype = col.type.compile(dialect=dialect)
            ddl = f'ALTER TABLE {table.name} ADD COLUMN "{col.name}" {coltype}'
            with engine.begin() as conn:
                conn.execute(text(ddl))


def init_db() -> None:
    """Create all tables. Import models so they register on the metadata."""
    import models  # noqa: F401  (registers mappers)

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
