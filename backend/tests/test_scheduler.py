"""Tests for the background auto-refresh cycle (no real timing/network)."""

from __future__ import annotations

from sqlmodel import select

from rss_reader import config, scheduler, service
from rss_reader.models import Item


def test_refresh_all_users_returns_per_user_results(session, client, feed_url):
    service.add_feed(session, feed_url, client=client)
    results = service.refresh_all_users(session, client=client)
    assert config.DEFAULT_USER_ID in results
    assert results[config.DEFAULT_USER_ID][0].new_count == 0  # already up to date


def test_run_refresh_cycle_refetches_missing_items(engine, session, client, feed_url):
    service.add_feed(session, feed_url, client=client)
    # Drop the items so the next cycle has something to re-add.
    for item in session.exec(select(Item)):
        session.delete(item)
    session.commit()

    total = scheduler.run_refresh_cycle(engine, client=client)
    assert total == 3
    assert len(service.list_items(session, days=None)) == 3
