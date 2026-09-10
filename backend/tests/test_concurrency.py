"""Database behaviour that only shows up against a real file.

The main fixture is an in-memory StaticPool engine sharing one connection, which
cannot reproduce WAL, locking or a second connection at all. Everything here
uses the file-backed engine instead, because a concurrency test against the
in-memory one proves nothing.
"""

from __future__ import annotations

import threading

import pytest
from sqlalchemy import text
from sqlmodel import Session, select

from rss_reader import service
from rss_reader.models import Feed, Item


def _pragma(engine, name: str):
    with engine.connect() as conn:
        return conn.execute(text(f"PRAGMA {name}")).scalar()


def test_the_pragmas_are_actually_set(file_engine):
    assert _pragma(file_engine, "journal_mode").lower() == "wal"
    assert _pragma(file_engine, "foreign_keys") == 1
    assert _pragma(file_engine, "busy_timeout") > 0


def test_every_connection_gets_them_not_just_the_first(file_engine):
    """They are per-connection, which is why they are on a connect event rather
    than next to create_engine."""
    with file_engine.connect() as first, file_engine.connect() as second:
        assert first.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert second.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_a_reader_is_not_blocked_by_an_open_write(file_engine, client, feed_url, user_id):
    """The 500-in-a-browser this is here to prevent: the background refresh
    commits while somebody's browser is polling for new items."""
    with Session(file_engine) as writer:
        service.add_feed(writer, feed_url, user_id, client=client)

    started = threading.Event()
    finished = threading.Event()

    def hold_a_write():
        with Session(file_engine) as session:
            session.exec(text("BEGIN IMMEDIATE"))
            session.exec(text("UPDATE items SET read = 1"))
            started.set()
            finished.wait(timeout=5)
            session.rollback()

    thread = threading.Thread(target=hold_a_write)
    thread.start()
    try:
        assert started.wait(timeout=5)
        with Session(file_engine) as reader:
            rows = reader.exec(select(Item)).all()
        assert len(rows) > 0
    finally:
        finished.set()
        thread.join(timeout=5)


def test_removing_a_feed_leaves_no_orphaned_items(file_engine, client, feed_url, user_id):
    """The risk introduced by turning this into bulk statements: delete the feed
    row and the items are still there, pointing at nothing."""
    with Session(file_engine) as session:
        feed = service.add_feed(session, feed_url, user_id, client=client)
        feed_id = feed.id
        assert session.exec(select(Item).where(Item.feed_id == feed_id)).all()

        service.remove_feed(session, feed_id, user_id)

        assert session.exec(select(Feed).where(Feed.id == feed_id)).all() == []
        assert session.exec(select(Item).where(Item.feed_id == feed_id)).all() == []


def test_a_failed_removal_leaves_the_feed_and_its_items_together(
    file_engine, client, feed_url, user_id, monkeypatch
):
    """Items are deleted first, so a failure part-way must roll both back rather
    than leaving items behind a feed that is already gone."""
    with Session(file_engine) as session:
        feed = service.add_feed(session, feed_url, user_id, client=client)
        feed_id = feed.id

        real_commit = session.commit
        monkeypatch.setattr(
            session, "commit", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        with pytest.raises(RuntimeError):
            service.remove_feed(session, feed_id, user_id)
        monkeypatch.setattr(session, "commit", real_commit)
        session.rollback()

        assert session.exec(select(Feed).where(Feed.id == feed_id)).all()
        assert session.exec(select(Item).where(Item.feed_id == feed_id)).all()


def test_foreign_keys_refuse_an_item_with_no_feed(file_engine):
    """foreign_keys=ON is what makes the orphan case an error rather than a row
    nobody notices until a count goes wrong."""
    import sqlalchemy as sa

    from rss_reader.models import _utcnow

    with Session(file_engine) as session:
        session.add(
            Item(
                feed_id=9999,
                guid="x",
                title="orphan",
                published_at=_utcnow(),
            )
        )
        with pytest.raises(sa.exc.IntegrityError):
            session.commit()
