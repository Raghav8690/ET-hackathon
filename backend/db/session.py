"""
PS8 – Database Session & Engine Configuration

Provides:
- ``engine``   : The SQLAlchemy engine (SQLite for dev, PostgreSQL for prod).
- ``SessionLocal`` : A configured session factory.
- ``get_db()``     : FastAPI dependency that yields a session and ensures cleanup.
- ``init_db()``    : Creates all tables defined in ``models.py``.

Configuration
-------------
Set the ``DATABASE_URL`` environment variable to override the default SQLite
database.  For PostgreSQL, use:

    DATABASE_URL=postgresql://user:pass@host:5432/ps8_db

If ``DATABASE_URL`` is unset, a local SQLite file at
``<project_root>/data/ps8_dev.db`` is used automatically.
"""

import os
from pathlib import Path
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.db.models import Base

# ---------------------------------------------------------------------------
# Load .env from project root (two levels up from this file)
# ---------------------------------------------------------------------------
_project_root = Path(__file__).resolve().parents[2]  # backend/db/session.py → project root
load_dotenv(_project_root / ".env")

# ---------------------------------------------------------------------------
# Resolve database URL
# ---------------------------------------------------------------------------
DATABASE_URL: str = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    # Default: SQLite stored under <project_root>/data/
    _data_dir = _project_root / "data"
    _data_dir.mkdir(parents=True, exist_ok=True)
    _db_path = _data_dir / "ps8_dev.db"
    DATABASE_URL = f"sqlite:///{_db_path}"

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
_connect_args: dict = {}

if DATABASE_URL.startswith("sqlite"):
    # SQLite requires `check_same_thread=False` for FastAPI's threaded model
    _connect_args["check_same_thread"] = False

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    echo=False,  # Set True for SQL debug logging
    pool_pre_ping=True,  # Verify connections before handing them out
)


# Enable WAL mode and foreign key enforcement for SQLite
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------
def get_db() -> Generator[Session, None, None]:
    """Yield a database session for the lifetime of a single request.

    Usage in a FastAPI route::

        @app.get("/items")
        def list_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Table initialisation
# ---------------------------------------------------------------------------
def init_db() -> None:
    """Create all tables that don't already exist.

    Safe to call multiple times – ``create_all`` is a no-op for existing
    tables.
    """
    Base.metadata.create_all(bind=engine)


def drop_db() -> None:
    """Drop all tables.  **Use only for tests / development.**"""
    Base.metadata.drop_all(bind=engine)
