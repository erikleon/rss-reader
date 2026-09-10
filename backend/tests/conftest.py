"""Shared test fixtures: in-memory DB and an httpx client backed by a local fixture.

Two users exist in every fixture, not one. The ownership checks in the service
layer were written long before anybody could exercise them, and a suite with a
single user cannot tell a scoped query from an unscoped one.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
from sqlalchemy import event
from sqlmodel import Session, SQLModel, StaticPool, create_engine

from rss_reader import config
from rss_reader.db import _apply_pragmas
from rss_reader.models import User

OWNER_LOGIN = "owner@example.com"
OTHER_LOGIN = "other@example.com"


@pytest.fixture(autouse=True)
def _offline_fetches(monkeypatch):
    """Turn off the SSRF guard for the offline suite.

    These tests fetch example.com and nofeed.example through a MockTransport.
    The guard resolves hostnames for real, so it would reject the second and
    make the first depend on DNS. The guard's own behaviour is tested directly
    in test_fetch_guard.py with a fake resolver.
    """
    monkeypatch.setattr(config, "FETCH_GUARD", False)

FIXTURE = Path(__file__).parent / "sample_feed.xml"
HOME_FIXTURE = Path(__file__).parent / "sample_home.html"
FEED_ETAG = '"feed-v1"'


@pytest.fixture
def engine():
    """A fresh in-memory SQLite engine with the schema and two users seeded."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", _apply_pragmas)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id=config.DEFAULT_USER_ID, username=OWNER_LOGIN))
        session.add(User(username=OTHER_LOGIN))
        session.commit()
    return engine


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def user_id() -> int:
    """The user every single-owner test operates as."""
    return config.DEFAULT_USER_ID


@pytest.fixture
def other_id(session) -> int:
    """A second user, so scoping can be asserted rather than assumed."""
    from sqlmodel import select

    return session.exec(select(User).where(User.username == OTHER_LOGIN)).one().id


@pytest.fixture
def file_engine(tmp_path):
    """A file-backed engine, for anything that depends on WAL or on locking.

    The in-memory StaticPool engine above shares one connection and cannot
    reproduce either, so a concurrency test against it proves nothing.
    """
    os.environ["RSS_READER_DB"] = str(tmp_path / "rss_reader.db")
    engine = create_engine(
        f"sqlite:///{tmp_path / 'rss_reader.db'}",
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _apply_pragmas)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id=config.DEFAULT_USER_ID, username=OWNER_LOGIN))
        session.commit()
    yield engine
    engine.dispose()
    os.environ.pop("RSS_READER_DB", None)


def _handler(request: httpx.Request) -> httpx.Response:
    """Serve local fixtures without touching the network.

    For host example.com: the bare homepage ("/") returns an HTML page that
    advertises the feed (for autodiscovery tests); "/feed.xml" and other paths
    return the RSS fixture. Everything else 404s.
    """
    if request.url.host == "example.com":
        if request.url.path in ("", "/"):
            return httpx.Response(
                200,
                content=HOME_FIXTURE.read_bytes(),
                headers={"content-type": "text/html"},
            )
        # Conditional GET: 304 when the client already has the current version.
        if request.headers.get("if-none-match") == FEED_ETAG:
            return httpx.Response(304, headers={"etag": FEED_ETAG})
        return httpx.Response(
            200,
            content=FIXTURE.read_bytes(),
            headers={
                "content-type": "application/rss+xml",
                "etag": FEED_ETAG,
                "last-modified": "Wed, 07 Jan 2026 00:00:00 GMT",
            },
        )
    if request.url.host == "nofeed.example":
        # A valid HTML page that advertises no feed.
        return httpx.Response(
            200,
            content=b"<html><head><title>No feed here</title></head><body>hi</body></html>",
            headers={"content-type": "text/html"},
        )
    return httpx.Response(404, text="not found")


@pytest.fixture
def client():
    """An httpx.Client that returns the fixture without touching the network."""
    transport = httpx.MockTransport(_handler)
    with httpx.Client(transport=transport) as c:
        yield c


@pytest.fixture
def feed_url() -> str:
    return "https://example.com/feed.xml"
