"""Tests for Alembic-backed database initialization."""

from __future__ import annotations

from sqlalchemy import inspect
from sqlmodel import Session, SQLModel, create_engine

from rss_reader import config, db
from rss_reader.models import User


def _file_engine(tmp_path):
    return create_engine(f"sqlite:///{tmp_path / 'test.db'}")


def test_init_db_creates_schema_and_default_user(tmp_path):
    engine = _file_engine(tmp_path)
    db.init_db(engine)

    tables = set(inspect(engine).get_table_names())
    assert {"users", "feeds", "items", "alembic_version"} <= tables
    with Session(engine) as session:
        assert session.get(User, config.DEFAULT_USER_ID) is not None


def test_init_db_stamps_preexisting_database(tmp_path):
    engine = _file_engine(tmp_path)
    # Simulate a database created before Alembic was adopted (raw create_all,
    # no alembic_version table).
    SQLModel.metadata.create_all(engine)
    assert "alembic_version" not in inspect(engine).get_table_names()

    db.init_db(engine)  # should stamp, not error on already-present tables

    assert "alembic_version" in inspect(engine).get_table_names()


def test_init_db_is_idempotent(tmp_path):
    engine = _file_engine(tmp_path)
    db.init_db(engine)
    db.init_db(engine)  # second run is a no-op upgrade
    with Session(engine) as session:
        assert session.get(User, config.DEFAULT_USER_ID) is not None
