"""Database models.

Multi-user readiness: every ``Feed`` carries a ``user_id`` and ``Item`` rows hang
off a feed, so per-item read state is a plain boolean (it is naturally scoped to a
user because the feed is). Adding auth later means resolving a real user id instead
of the default one — no schema change to read state.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel, UniqueConstraint


def _utcnow() -> datetime:
    # Store naive UTC consistently so SQLite comparisons never mix tz-aware and
    # tz-naive values. Read-back values are interpreted as UTC.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    username: str | None = Field(default=None, unique=True)
    created_at: datetime = Field(default_factory=_utcnow)
    # Auth fields (password_hash, etc.) are intentionally deferred.


class Feed(SQLModel, table=True):
    __tablename__ = "feeds"
    __table_args__ = (UniqueConstraint("user_id", "url", name="uq_feed_user_url"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(default=1, foreign_key="users.id", index=True)
    url: str
    title: str
    site_url: str | None = None
    added_at: datetime = Field(default_factory=_utcnow)
    last_fetched_at: datetime | None = None
    last_error: str | None = None


class Item(SQLModel, table=True):
    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("feed_id", "guid", name="uq_item_feed_guid"),)

    id: int | None = Field(default=None, primary_key=True)
    feed_id: int = Field(foreign_key="feeds.id", index=True)
    guid: str
    title: str
    link: str | None = None
    summary: str | None = None
    published_at: datetime = Field(index=True)
    fetched_at: datetime = Field(default_factory=_utcnow)
    read: bool = Field(default=False, index=True)
