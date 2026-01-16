"""Shared test fixtures: in-memory DB and an httpx client backed by a local fixture."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlmodel import Session, SQLModel, StaticPool, create_engine

from rss_reader import config
from rss_reader.models import User

FIXTURE = Path(__file__).parent / "sample_feed.xml"
HOME_FIXTURE = Path(__file__).parent / "sample_home.html"
FEED_ETAG = '"feed-v1"'


@pytest.fixture
def engine():
    """A fresh in-memory SQLite engine with the schema and default user seeded."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id=config.DEFAULT_USER_ID, username="default"))
        session.commit()
    return engine


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session


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
