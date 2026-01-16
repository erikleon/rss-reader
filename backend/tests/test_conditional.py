"""Tests for conditional GET (ETag / Last-Modified) during refresh."""

from __future__ import annotations

from rss_reader import fetcher, service


def test_fetch_conditional_captures_validators(client, feed_url):
    result = fetcher.fetch_conditional(feed_url, client=client)
    assert result.not_modified is False
    assert result.parsed is not None
    assert result.etag == '"feed-v1"'
    assert result.last_modified == "Wed, 07 Jan 2026 00:00:00 GMT"


def test_fetch_conditional_returns_304_when_etag_matches(client, feed_url):
    first = fetcher.fetch_conditional(feed_url, client=client)
    second = fetcher.fetch_conditional(feed_url, etag=first.etag, client=client)
    assert second.not_modified is True
    assert second.parsed is None


def test_refresh_stores_validators(session, client, feed_url):
    service.add_feed(session, feed_url, client=client)
    service.refresh_all(session, client=client)
    feed = service.list_feeds(session)[0]
    assert feed.etag == '"feed-v1"'
    assert feed.last_modified == "Wed, 07 Jan 2026 00:00:00 GMT"


def test_refresh_not_modified_keeps_items_and_succeeds(session, client, feed_url):
    service.add_feed(session, feed_url, client=client)
    service.refresh_all(session, client=client)  # stores the etag
    # Second refresh sends the etag and gets a 304.
    results = service.refresh_all(session, client=client)
    assert results[0].error is None
    assert results[0].new_count == 0
    assert len(service.list_items(session, days=None)) == 3
