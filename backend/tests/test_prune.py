"""Tests for retention / pruning of old items."""

from __future__ import annotations

from rss_reader import service

# The sample fixture items are dated January 2026, i.e. several months old
# relative to the test clock, so a 30-day window treats them as "old".


def test_prune_deletes_old_read_items(session, client, feed_url, user_id):
    service.add_feed(session, feed_url, user_id, client=client)
    service.mark_all_read(session, user_id)
    deleted = service.prune_items(session, user_id, days=30)
    assert deleted == 3
    assert service.list_items(session, user_id, days=None) == []


def test_prune_keeps_unread_by_default(session, client, feed_url, user_id):
    service.add_feed(session, feed_url, user_id, client=client)
    deleted = service.prune_items(session, user_id, days=30)
    assert deleted == 0
    assert len(service.list_items(session, user_id, days=None)) == 3


def test_prune_all_includes_unread(session, client, feed_url, user_id):
    service.add_feed(session, feed_url, user_id, client=client)
    deleted = service.prune_items(session, user_id, days=30, include_unread=True)
    assert deleted == 3


def test_prune_respects_window(session, client, feed_url, user_id):
    service.add_feed(session, feed_url, user_id, client=client)
    service.mark_all_read(session, user_id)
    # A century-wide window: nothing is older than the cutoff.
    deleted = service.prune_items(session, user_id, days=36500)
    assert deleted == 0
    assert len(service.list_items(session, user_id, days=None)) == 3


def test_prune_disabled_when_days_zero(session, client, feed_url, user_id):
    service.add_feed(session, feed_url, user_id, client=client)
    service.mark_all_read(session, user_id)
    assert service.prune_items(session, user_id, days=0) == 0
