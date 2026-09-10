"""Engine, session handling, and schema initialization."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import event, inspect
from sqlmodel import Session, create_engine

from . import config

_MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"

_engine = None


def _apply_pragmas(dbapi_connection, _record) -> None:
    """Set the pragmas SQLite does not keep between connections.

    All three are per-connection, so they belong on a connect event rather than
    next to create_engine: a pool that opens a second connection would otherwise
    get none of them.

    WAL lets readers carry on through the background refresh's commit instead of
    blocking on it. busy_timeout turns the residual writer collision into a wait
    rather than an immediate error. foreign_keys is off by default in SQLite,
    which means a feed can be deleted out from under its items with nothing to
    stop it.
    """
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={int(config.SQLITE_BUSY_TIMEOUT * 1000)}")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def get_engine():
    """Lazily create the process-wide SQLite engine."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            config.database_url(),
            connect_args={"check_same_thread": False},
        )
        event.listen(_engine, "connect", _apply_pragmas)
    return _engine


def _alembic_config(engine):
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", str(engine.url))
    return cfg


def _migrate(engine) -> None:
    """Bring the schema to head via Alembic.

    A database created before Alembic was adopted has the tables but no
    ``alembic_version``. Stamp it at the revision matching the columns it
    actually has, then upgrade. Stamping straight at head, which is what this
    did before, would skip 0003 and leave ``users.username`` nullable on exactly
    the databases that need it changed.
    """
    from alembic import command

    cfg = _alembic_config(engine)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if "feeds" in tables and "alembic_version" not in tables:
        command.stamp(cfg, _revision_matching(inspector, tables))
    command.upgrade(cfg, "head")


def _revision_matching(inspector, tables: list[str]) -> str:
    """Which revision an un-stamped database already matches.

    Newest evidence first. Stamping too early makes the next upgrade try to
    create something that is already there; stamping at head, which this did
    originally, skips migrations the database genuinely needs.
    """
    if "articles" in tables:
        return "0004_article"
    users = {c["name"]: c for c in inspector.get_columns("users")}
    if not users.get("username", {}).get("nullable", True):
        return "0003_user_login"
    if "etag" in {c["name"] for c in inspector.get_columns("feeds")}:
        return "0002_feed_conditional_get"
    return "0001_baseline"


def init_db(engine=None) -> None:
    """Apply migrations. Users are created when a login first arrives."""
    engine = engine or get_engine()
    _migrate(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    with Session(get_engine()) as session:
        yield session


@contextmanager
def session_scope(engine=None) -> Iterator[Session]:
    """Transactional session: commits on success, rolls back on error."""
    engine = engine or get_engine()
    # expire_on_commit=False so ORM objects stay usable after the session
    # commits/closes — callers (CLI, etc.) read attributes after the `with` block.
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
