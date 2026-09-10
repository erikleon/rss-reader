"""Database models.

Every ``Feed`` carries a ``user_id`` and ``Item`` rows hang off a feed, so
per-item read state is a plain boolean: it is scoped to a user because the feed
is. That is what let auth be added without touching read state.

``User.username`` holds the Tailscale login the person arrives with, normalized
to lower case. It is the join between an incoming request and the rows below it,
so it is unique and not null.
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
    # The Tailscale login, lower-cased. There is no password_hash and there is
    # not meant to be: identity comes from the ingress, not from this table.
    username: str = Field(unique=True)
    created_at: datetime = Field(default_factory=_utcnow)


class Feed(SQLModel, table=True):
    __tablename__ = "feeds"
    __table_args__ = (UniqueConstraint("user_id", "url", name="uq_feed_user_url"),)

    id: int | None = Field(default=None, primary_key=True)
    # No default. A feed without an owner is not a thing that should be
    # constructible, for the same reason service functions lost theirs.
    user_id: int = Field(foreign_key="users.id", index=True)
    url: str
    title: str
    site_url: str | None = None
    added_at: datetime = Field(default_factory=_utcnow)
    last_fetched_at: datetime | None = None
    last_error: str | None = None
    # HTTP validators for conditional GET, so unchanged feeds return 304.
    etag: str | None = None
    last_modified: str | None = None


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
