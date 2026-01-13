"""Tests for feed autodiscovery from HTML pages."""

from __future__ import annotations

from pathlib import Path

import pytest

from rss_reader import fetcher, service

HOME = Path(__file__).parent / "sample_home.html"


def test_discover_feed_links_resolves_relative_href():
    links = fetcher.discover_feed_links(HOME.read_bytes(), "https://example.com/")
    assert links == ["https://example.com/feed.xml"]


def test_discover_feed_links_ignores_non_feed_links():
    html = '<link rel="icon" href="/favicon.ico">'
    assert fetcher.discover_feed_links(html, "https://example.com/") == []


def test_fetch_autodiscover_uses_feed_url_directly(client, feed_url):
    resolved, parsed = fetcher.fetch_feed_autodiscover(feed_url, client=client)
    assert resolved == feed_url
    assert parsed.is_feed
    assert len(parsed.entries) == 3


def test_fetch_autodiscover_from_homepage(client):
    resolved, parsed = fetcher.fetch_feed_autodiscover(
        "https://example.com/", client=client
    )
    assert resolved == "https://example.com/feed.xml"
    assert parsed.is_feed


def test_fetch_autodiscover_raises_when_no_feed(client):
    with pytest.raises(fetcher.FeedDiscoveryError):
        fetcher.fetch_feed_autodiscover("https://nofeed.example/", client=client)


def test_add_feed_via_homepage_stores_resolved_url(session, client):
    feed = service.add_feed(session, "https://example.com/", client=client)
    assert feed.url == "https://example.com/feed.xml"
    assert len(service.list_items(session, days=None)) == 3


def test_add_feed_rejects_duplicate_after_discovery(session, client):
    service.add_feed(session, "https://example.com/feed.xml", client=client)
    # Adding the homepage should resolve to the same feed and be rejected.
    with pytest.raises(service.FeedError):
        service.add_feed(session, "https://example.com/", client=client)
