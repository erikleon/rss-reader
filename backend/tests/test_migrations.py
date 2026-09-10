"""Tests for Alembic-backed database initialization."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlmodel import Session, SQLModel, create_engine, select

from rss_reader import config, db
from rss_reader.models import User


def _file_engine(tmp_path, name="test.db"):
    return create_engine(f"sqlite:///{tmp_path / name}")


def test_init_db_creates_schema_and_no_users(tmp_path):
    engine = _file_engine(tmp_path)
    db.init_db(engine)

    tables = set(inspect(engine).get_table_names())
    assert {"users", "feeds", "items", "alembic_version"} <= tables
    with Session(engine) as session:
        # No seeded account. A user exists only once a real login arrives, so
        # there is never a row an unidentified request could fall back to.
        assert session.exec(select(User)).all() == []


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
    assert "alembic_version" in inspect(engine).get_table_names()


# The 0001 schema, written out rather than generated. The point is to be the
# shape 0003 has to cope with on a real box, not the shape the current models
# produce. No etag column, so init_db must stamp this at 0001 and then run both
# 0002 and 0003 over it.
_LEGACY_DDL = [
    "CREATE TABLE users ("
    " id INTEGER NOT NULL PRIMARY KEY,"
    " username VARCHAR,"
    " created_at DATETIME NOT NULL,"
    " UNIQUE (username))",
    "CREATE TABLE feeds ("
    " id INTEGER NOT NULL PRIMARY KEY,"
    " user_id INTEGER NOT NULL,"
    " url VARCHAR NOT NULL,"
    " title VARCHAR NOT NULL,"
    " site_url VARCHAR,"
    " added_at DATETIME NOT NULL,"
    " last_fetched_at DATETIME,"
    " last_error VARCHAR,"
    " FOREIGN KEY(user_id) REFERENCES users (id),"
    " CONSTRAINT uq_feed_user_url UNIQUE (user_id, url))",
    "CREATE TABLE items ("
    " id INTEGER NOT NULL PRIMARY KEY,"
    " feed_id INTEGER NOT NULL,"
    " guid VARCHAR NOT NULL,"
    " title VARCHAR NOT NULL,"
    " link VARCHAR,"
    " summary VARCHAR,"
    " published_at DATETIME NOT NULL,"
    " fetched_at DATETIME NOT NULL,"
    " read BOOLEAN NOT NULL,"
    " FOREIGN KEY(feed_id) REFERENCES feeds (id),"
    " CONSTRAINT uq_item_feed_guid UNIQUE (feed_id, guid))",
]


def _legacy_database(tmp_path, name):
    """A pre-Alembic database: all three tables, nullable username, no version."""
    engine = _file_engine(tmp_path, name)
    with engine.begin() as conn:
        for statement in _LEGACY_DDL:
            conn.execute(sa.text(statement))
    return engine


def test_migration_0003_keeps_the_placeholder_row(tmp_path):
    """The pre-auth account survives so its feeds stay with whoever added them."""
    engine = _legacy_database(tmp_path, "legacy.db")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO users (id, username, created_at) "
                "VALUES (1, :name, '2026-01-01 00:00:00')"
            ),
            {"name": config.LEGACY_USERNAME},
        )

    db.init_db(engine)

    with Session(engine) as session:
        user = session.get(User, config.DEFAULT_USER_ID)
        assert user is not None
        assert user.username == config.LEGACY_USERNAME
    username = next(c for c in inspect(engine).get_columns("users") if c["name"] == "username")
    assert username["nullable"] is False


def test_migration_0003_names_rows_that_had_no_username(tmp_path):
    """A null username cannot be claimed by a login, so it gets a synthetic one.

    Deleting the row instead would take its feeds with it.
    """
    engine = _legacy_database(tmp_path, "nulls.db")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO users (id, username, created_at) "
                "VALUES (7, NULL, '2026-01-01 00:00:00')"
            )
        )

    db.init_db(engine)

    with Session(engine) as session:
        assert session.get(User, 7).username == "user-7"


def test_username_stays_unique_after_the_table_rebuild(tmp_path):
    """0003 rebuilds the table, which is exactly where a constraint gets lost."""
    engine = _file_engine(tmp_path, "dupes.db")
    db.init_db(engine)
    with Session(engine) as session:
        session.add(User(username="someone@example.com"))
        session.commit()
        session.add(User(username="someone@example.com"))
        with pytest.raises(sa.exc.IntegrityError):
            session.commit()
