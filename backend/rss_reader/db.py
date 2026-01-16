"""Engine, session handling, and schema/seed initialization."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import inspect
from sqlmodel import Session, create_engine

from . import config
from .models import User

_MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"

_engine = None


def get_engine():
    """Lazily create the process-wide SQLite engine."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            config.database_url(),
            connect_args={"check_same_thread": False},
        )
    return _engine


def _alembic_config(engine):
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", str(engine.url))
    return cfg


def _migrate(engine) -> None:
    """Bring the schema to head via Alembic.

    A database created before Alembic was adopted already has the tables but no
    ``alembic_version``; stamp it at head rather than re-creating, then future
    migrations apply normally.
    """
    from alembic import command

    cfg = _alembic_config(engine)
    tables = inspect(engine).get_table_names()
    if "feeds" in tables and "alembic_version" not in tables:
        command.stamp(cfg, "head")
    else:
        command.upgrade(cfg, "head")


def init_db(engine=None) -> None:
    """Apply migrations and ensure the default user exists."""
    engine = engine or get_engine()
    _migrate(engine)
    with Session(engine) as session:
        existing = session.get(User, config.DEFAULT_USER_ID)
        if existing is None:
            session.add(User(id=config.DEFAULT_USER_ID, username="default"))
            session.commit()


@contextmanager
def session_scope(engine=None) -> Iterator[Session]:
    """Transactional session: commits on success, rolls back on error."""
    engine = engine or get_engine()
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
