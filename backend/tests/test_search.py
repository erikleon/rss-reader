"""Tests for item search."""

from __future__ import annotations

from rss_reader import service


def test_search_matches_title_case_insensitive(session, client, feed_url):
    service.add_feed(session, feed_url, client=client)
    results = service.list_items(session, days=None, query="first")
    assert len(results) == 1
    assert results[0].title == "First Post"
    # Case-insensitive.
    assert len(service.list_items(session, days=None, query="FIRST")) == 1


def test_search_matches_summary(session, client, feed_url):
    service.add_feed(session, feed_url, client=client)
    # "plain text summary" is in the second item's description only.
    results = service.list_items(session, days=None, query="plain text")
    assert len(results) == 1
    assert results[0].title == "Second Post"


def test_search_no_match_returns_empty(session, client, feed_url):
    service.add_feed(session, feed_url, client=client)
    assert service.list_items(session, days=None, query="nonexistent-term") == []


def test_blank_query_is_ignored(session, client, feed_url):
    service.add_feed(session, feed_url, client=client)
    assert len(service.list_items(session, days=None, query="   ")) == 3
