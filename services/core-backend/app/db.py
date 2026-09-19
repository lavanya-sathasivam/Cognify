"""COGNIFY core-backend — database configuration (SQLite for development).

Separation of concerns:
- This module owns engine / session / Base configuration ONLY.
- Table definitions live in ``app/models.py``.
- CRUD lives in ``app/repositories.py`` (functions take a Session; they never
  create engines or read env vars).

The AI service MUST NOT import this module or access this database directly;
it talks to core-backend over HTTP. Only core-backend owns learner state.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for all core-backend tables."""


DEFAULT_SQLITE_URL: str = "sqlite:///./cognify_dev.db"


def get_database_url() -> str:
    """Database URL for core-backend.

    Defaults to file-backed SQLite for development. Override with
    ``DATABASE_URL`` env var (e.g. Postgres in later steps).
    """
    return os.getenv("DATABASE_URL", DEFAULT_SQLITE_URL)


def _enable_sqlite_fk(dbapi_conn, _conn_record) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine(url: str | None = None, echo: bool = False) -> Engine:
    """Create a SQLAlchemy engine (SQLite FK enforcement enabled)."""
    from sqlalchemy import create_engine

    db_url = url or get_database_url()
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    engine = create_engine(db_url, connect_args=connect_args, echo=echo, future=True)
    if db_url.startswith("sqlite"):
        event.listen(engine, "connect", _enable_sqlite_fk)
    return engine


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Session factory bound to ``engine`` (expire_on_commit=False for tests)."""
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """Transactional scope: commits on success, rolls back on error."""
    factory = get_session_factory(engine)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(engine: Engine):
    """Create all tables (imports models so they register on Base)."""
    from . import models  # noqa: F401  (register tables)

    Base.metadata.create_all(bind=engine)
    return engine


__all__ = [
    "Base",
    "DEFAULT_SQLITE_URL",
    "get_database_url",
    "get_engine",
    "get_session_factory",
    "init_db",
    "session_scope",
]
