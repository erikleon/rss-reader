"""Tests for the core service layer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlmodel import select

from rss_reader import service
from rss_reader.models import Item


def test_add_feed_stores_metadata_and_items(session, client, feed_url):
    feed = service.add_feed(session, feed_url, client=client)
    assert feed.id is not None
    assert feed.title == "Example Tech Blog"
    assert feed.site_url == "https://example.com"
    items = service.list_items(session, days=None)
    assert len(items) == 3


def test_add_feed_rejects_duplicate(session, client, feed_url):
    service.add_feed(session, feed_url, client=client)
    with pytest.raises(service.FeedError):
        service.add_feed(session, feed_url, client=client)


def test_add_feed_rejects_unreachable(session, client):
    with pytest.raises(service.FeedError):
        service.add_feed(session, "https://nope.invalid/feed", client=client)


def test_refresh_dedupes_existing_items(session, client, feed_url):
    service.add_feed(session, feed_url, client=client)
    results = service.refresh_all(session, client=client)
    assert len(results) == 1
    assert results[0].new_count == 0  # everything already present
    assert results[0].error is None
    assert len(service.list_items(session, days=None)) == 3


def test_refresh_isolates_feed_errors(session, client, feed_url):
    service.add_feed(session, feed_url, client=client)

    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    failing = httpx.Client(transport=httpx.MockTransport(failing_handler))
    results = service.refresh_all(session, client=failing)
    assert results[0].error is not None
    # The error is recorded on the feed row.
    feed = service.list_feeds(session)[0]
    assert feed.last_error is not None


def test_set_read_and_unread(session, client, feed_url):
    service.add_feed(session, feed_url, client=client)
    item = service.list_items(session, days=None)[0]
    assert item.read is False
    service.set_read(session, item.id, True)
    assert service.list_items(session, days=None, unread_only=True).__len__() == 2
    service.set_read(session, item.id, False)
    assert len(service.list_items(session, days=None, unread_only=True)) == 3


def test_mark_all_read(session, client, feed_url):
    service.add_feed(session, feed_url, client=client)
    changed = service.mark_all_read(session)
    assert changed == 3
    assert service.list_items(session, days=None, unread_only=True) == []


def test_list_items_respects_day_window(session, client, feed_url):
    service.add_feed(session, feed_url, client=client)
    # The fixture items are dated Jan 2026; a tiny window excludes them all.
    recent = service.list_items(session, days=1)
    assert recent == []
    everything = service.list_items(session, days=None)
    assert len(everything) == 3


def test_remove_feed_deletes_items(session, client, feed_url):
    feed = service.add_feed(session, feed_url, client=client)
    service.remove_feed(session, feed.id)
    assert service.list_feeds(session) == []
    assert list(session.exec(select(Item))) == []


def test_group_by_day_buckets_local_dates(session, client, feed_url):
    service.add_feed(session, feed_url, client=client)
    items = service.list_items(session, days=None)
    groups = service.group_by_day(items)
    # Three items across two source days (Jan 5 and Jan 6 UTC).
    assert sum(len(g.items) for g in groups) == 3
    # Newest first: group days are in descending order.
    days = [g.day for g in groups]
    assert days == sorted(days, reverse=True)
