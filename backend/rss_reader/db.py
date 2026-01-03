"""Engine, session handling, and schema/seed initialization."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine

from . import config
from .models import User

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


def init_db(engine=None) -> None:
    """Create tables (if needed) and ensure the default user exists."""
    engine = engine or get_engine()
    SQLModel.metadata.create_all(engine)
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
