"""Shared test fixtures: in-memory DB and an httpx client backed by a local fixture."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlmodel import Session, SQLModel, StaticPool, create_engine

from rss_reader import config
from rss_reader.models import User

FIXTURE = Path(__file__).parent / "sample_feed.xml"


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
    """Serve the local fixture for the example feed; 404 for anything else."""
    if request.url.host == "example.com":
        return httpx.Response(200, content=FIXTURE.read_bytes())
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
