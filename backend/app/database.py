"""Database engine + session management (SQLAlchemy 2.0).

Default storage is SQLite so the system runs with zero external setup,
but `DATABASE_URL` may point to PostgreSQL (or MongoDB via a wrapper)
in production. All repositories use SQLAlchemy so swapping engines is a
config-only change.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

connect_args = (
    {"check_same_thread": False}
    if settings.DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001
    if settings.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema() -> None:
    """Create tables and apply lightweight column migrations.

    ``create_all`` only creates missing tables, so columns added after the
    first deploy need an explicit ``ALTER TABLE`` for existing databases.
    """
    Base.metadata.create_all(bind=engine)
    if settings.DATABASE_URL.startswith("sqlite"):
        inspector = inspect(engine)
        if "documents" in inspector.get_table_names():
            columns = {c["name"] for c in inspector.get_columns("documents")}
            if "expected_doc_type" not in columns:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE documents ADD COLUMN expected_doc_type VARCHAR(50) DEFAULT ''"))
            if "forgery" not in columns:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE documents ADD COLUMN forgery JSON"))
    # TODO: mirror the ALTER above for PostgreSQL if a migration tool is adopted.
