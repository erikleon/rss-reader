"""Core operations shared by the web API and the CLI.

Every function takes a ``Session`` and a ``user_id`` (defaulting to the single
current user). Queries are scoped by ``user_id`` so adding auth later is additive.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlmodel import Session, select

from . import config, fetcher, opml
from .fetcher import ParsedFeed
from .models import Feed, Item, User


class FeedError(Exception):
    """Raised for user-facing feed problems (unreachable, missing, etc.)."""


class DuplicateFeedError(FeedError):
    """Raised when subscribing to a feed that already exists."""


def _to_naive_utc(dt: datetime) -> datetime:
    """Normalize any datetime to naive UTC for storage."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


# --------------------------------------------------------------------------- #
# Feeds
# --------------------------------------------------------------------------- #
def list_feeds(session: Session, user_id: int = config.DEFAULT_USER_ID) -> list[Feed]:
    stmt = select(Feed).where(Feed.user_id == user_id).order_by(Feed.title)
    return list(session.exec(stmt))


def _feed_for_url(session: Session, url: str, user_id: int) -> Feed | None:
    return session.exec(
        select(Feed).where(Feed.user_id == user_id, Feed.url == url)
    ).first()


def _get_feed(session: Session, feed_id: int, user_id: int) -> Feed:
    feed = session.get(Feed, feed_id)
    if feed is None or feed.user_id != user_id:
        raise FeedError(f"Feed {feed_id} not found")
    return feed


def add_feed(
    session: Session,
    url: str,
    user_id: int = config.DEFAULT_USER_ID,
    *,
    client: httpx.Client | None = None,
) -> Feed:
    """Subscribe to ``url``: fetch (with feed autodiscovery), then pull items.

    If ``url`` points at a site homepage rather than a feed, the feed URL is
    discovered from the page's ``<link rel="alternate">`` tags and stored instead.
    """
    url = url.strip()
    if _feed_for_url(session, url, user_id) is not None:
        raise DuplicateFeedError(f"Already subscribed to {url}")

    try:
        resolved_url, parsed = fetcher.fetch_feed_autodiscover(url, client=client)
    except httpx.HTTPError as exc:
        raise FeedError(f"Could not fetch {url}: {exc}") from exc
    except fetcher.FeedDiscoveryError as exc:
        raise FeedError(str(exc)) from exc

    # Autodiscovery may have resolved to a different URL already subscribed to.
    if resolved_url != url and _feed_for_url(session, resolved_url, user_id) is not None:
        raise DuplicateFeedError(f"Already subscribed to {resolved_url}")

    feed = Feed(
        user_id=user_id,
        url=resolved_url,
        title=parsed.title,
        site_url=parsed.site_url,
        last_fetched_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    session.add(feed)
    session.flush()  # assign feed.id

    _upsert_items(session, feed, parsed)
    session.commit()
    session.refresh(feed)
    return feed


@dataclass
class ImportResult:
    added: list[str]                  # titles of newly subscribed feeds
    skipped: list[str]                # URLs already subscribed to
    failed: list[tuple[str, str]]     # (url, error message)


def import_opml(
    session: Session,
    content: bytes | str,
    user_id: int = config.DEFAULT_USER_ID,
    *,
    client: httpx.Client | None = None,
) -> ImportResult:
    """Subscribe to every feed in an OPML document, isolating per-feed failures."""
    result = ImportResult(added=[], skipped=[], failed=[])
    for entry in opml.parse_opml(content):
        try:
            feed = add_feed(session, entry.xml_url, user_id, client=client)
            result.added.append(feed.title)
        except DuplicateFeedError:
            result.skipped.append(entry.xml_url)
        except FeedError as exc:
            result.failed.append((entry.xml_url, str(exc)))
    return result


def remove_feed(
    session: Session, feed_id: int, user_id: int = config.DEFAULT_USER_ID
) -> None:
    feed = _get_feed(session, feed_id, user_id)
    for item in session.exec(select(Item).where(Item.feed_id == feed_id)):
        session.delete(item)
    session.delete(feed)
    session.commit()


# --------------------------------------------------------------------------- #
# Refresh
# --------------------------------------------------------------------------- #
@dataclass
class RefreshResult:
    feed_id: int
    title: str
    new_count: int
    error: str | None = None


def _upsert_items(session: Session, feed: Feed, parsed: ParsedFeed) -> int:
    """Insert entries not already stored for this feed. Returns new-item count."""
    existing_guids = set(
        session.exec(select(Item.guid).where(Item.feed_id == feed.id))
    )
    new_count = 0
    for entry in parsed.entries:
        if entry.guid in existing_guids:
            continue
        session.add(
            Item(
                feed_id=feed.id,
                guid=entry.guid,
                title=entry.title,
                link=entry.link,
                summary=entry.summary,
                published_at=_to_naive_utc(entry.published_at),
            )
        )
        existing_guids.add(entry.guid)
        new_count += 1
    return new_count


def _fetch_for_refresh(
    url: str, etag: str | None, last_modified: str | None, client: httpx.Client | None
) -> tuple[fetcher.FetchResult | None, str | None]:
    """Network-only part of a refresh; safe to run in a worker thread.

    Touches no ORM state — the feed URL and validators are passed in by value —
    so many feeds can be fetched concurrently while DB writes stay on the owning
    thread. Sends conditional-GET validators so unchanged feeds return 304.
    """
    try:
        result = fetcher.fetch_conditional(
            url, etag=etag, last_modified=last_modified, client=client
        )
        return result, None
    except Exception as exc:  # noqa: BLE001 - one bad feed must not abort others
        return None, str(exc)


def _apply_fetch(
    session: Session,
    feed: Feed,
    result: fetcher.FetchResult | None,
    error: str | None,
) -> RefreshResult:
    """DB-side part of a refresh; runs serially on the session's thread."""
    if error is not None:
        feed.last_error = error
        session.add(feed)
        return RefreshResult(feed.id, feed.title, 0, error=error)

    feed.last_fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
    feed.last_error = None
    if result.not_modified:
        # Unchanged since last fetch; nothing to upsert.
        session.add(feed)
        return RefreshResult(feed.id, feed.title, 0)

    new_count = _upsert_items(session, feed, result.parsed)
    feed.etag = result.etag
    feed.last_modified = result.last_modified
    session.add(feed)
    return RefreshResult(feed.id, feed.title, new_count)


def refresh_feed(
    session: Session,
    feed: Feed,
    *,
    client: httpx.Client | None = None,
) -> RefreshResult:
    """Refresh a single feed, capturing any error on the feed row."""
    result, error = _fetch_for_refresh(feed.url, feed.etag, feed.last_modified, client)
    return _apply_fetch(session, feed, result, error)


def refresh_all(
    session: Session,
    user_id: int = config.DEFAULT_USER_ID,
    *,
    client: httpx.Client | None = None,
) -> list[RefreshResult]:
    """Refresh every subscribed feed; fetches run in parallel, writes serially."""
    feeds = list_feeds(session, user_id)
    if not feeds:
        return []

    workers = min(config.REFRESH_CONCURRENCY, len(feeds))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        # Feed attributes are read here on the main thread, not in the worker.
        futures = [
            pool.submit(
                _fetch_for_refresh, feed.url, feed.etag, feed.last_modified, client
            )
            for feed in feeds
        ]
        fetched = [f.result() for f in futures]

    results = [
        _apply_fetch(session, feed, result, error)
        for feed, (result, error) in zip(feeds, fetched)
    ]
    session.commit()
    return results


def refresh_all_users(
    session: Session, *, client: httpx.Client | None = None
) -> dict[int, list[RefreshResult]]:
    """Refresh feeds for every user. Used by the background scheduler."""
    user_ids = list(session.exec(select(User.id)))
    return {uid: refresh_all(session, uid, client=client) for uid in user_ids}


# --------------------------------------------------------------------------- #
# Items / read state
# --------------------------------------------------------------------------- #
def list_items(
    session: Session,
    user_id: int = config.DEFAULT_USER_ID,
    *,
    days: int | None = config.DEFAULT_DAYS,
    unread_only: bool = False,
    before: datetime | None = None,
) -> list[Item]:
    """Items for the user's feeds, newest first, within an optional day window."""
    feed_ids = [f.id for f in list_feeds(session, user_id)]
    if not feed_ids:
        return []

    stmt = select(Item).where(Item.feed_id.in_(feed_ids))
    if days is not None:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        stmt = stmt.where(Item.published_at >= cutoff)
    if before is not None:
        stmt = stmt.where(Item.published_at < _to_naive_utc(before))
    if unread_only:
        stmt = stmt.where(Item.read == False)  # noqa: E712 - SQL boolean column
    stmt = stmt.order_by(Item.published_at.desc())
    return list(session.exec(stmt))


def set_read(
    session: Session,
    item_id: int,
    read: bool,
    user_id: int = config.DEFAULT_USER_ID,
) -> Item:
    item = session.get(Item, item_id)
    if item is None:
        raise FeedError(f"Item {item_id} not found")
    feed = session.get(Feed, item.feed_id)
    if feed is None or feed.user_id != user_id:
        raise FeedError(f"Item {item_id} not found")
    item.read = read
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def mark_all_read(session: Session, user_id: int = config.DEFAULT_USER_ID) -> int:
    """Mark every unread item read. Returns the number changed."""
    items = list_items(session, user_id, days=None, unread_only=True)
    for item in items:
        item.read = True
        session.add(item)
    session.commit()
    return len(items)


# --------------------------------------------------------------------------- #
# Grouping (used by the CLI; the frontend groups client-side in local time)
# --------------------------------------------------------------------------- #
@dataclass
class DayGroup:
    day: date
    items: list[Item]


def group_by_day(items: list[Item]) -> list[DayGroup]:
    """Bucket already-sorted items by their local calendar day, newest first."""
    groups: list[DayGroup] = []
    for item in items:
        local_day = (
            item.published_at.replace(tzinfo=timezone.utc).astimezone().date()
        )
        if groups and groups[-1].day == local_day:
            groups[-1].items.append(item)
        else:
            groups.append(DayGroup(day=local_day, items=[item]))
    return groups
