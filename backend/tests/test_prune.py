"""Tests for retention / pruning of old items."""

from __future__ import annotations

from rss_reader import service

# The sample fixture items are dated January 2026, i.e. several months old
# relative to the test clock, so a 30-day window treats them as "old".


def test_prune_deletes_old_read_items(session, client, feed_url):
    service.add_feed(session, feed_url, client=client)
    service.mark_all_read(session)
    deleted = service.prune_items(session, days=30)
    assert deleted == 3
    assert service.list_items(session, days=None) == []


def test_prune_keeps_unread_by_default(session, client, feed_url):
    service.add_feed(session, feed_url, client=client)
    deleted = service.prune_items(session, days=30)
    assert deleted == 0
    assert len(service.list_items(session, days=None)) == 3


def test_prune_all_includes_unread(session, client, feed_url):
    service.add_feed(session, feed_url, client=client)
    deleted = service.prune_items(session, days=30, include_unread=True)
    assert deleted == 3


def test_prune_respects_window(session, client, feed_url):
    service.add_feed(session, feed_url, client=client)
    service.mark_all_read(session)
    # A century-wide window: nothing is older than the cutoff.
    deleted = service.prune_items(session, days=36500)
    assert deleted == 0
    assert len(service.list_items(session, days=None)) == 3


def test_prune_disabled_when_days_zero(session, client, feed_url):
    service.add_feed(session, feed_url, client=client)
    service.mark_all_read(session)
    assert service.prune_items(session, days=0) == 0
