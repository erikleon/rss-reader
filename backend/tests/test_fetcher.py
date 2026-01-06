"""Tests for feed fetching and entry normalization (no network)."""

from __future__ import annotations

from datetime import timezone
from pathlib import Path

from rss_reader import fetcher

FIXTURE = Path(__file__).parent / "sample_feed.xml"


def test_parse_feed_metadata():
    parsed = fetcher.parse_feed(FIXTURE.read_bytes())
    assert parsed.title == "Example Tech Blog"
    assert parsed.site_url == "https://example.com"
    assert len(parsed.entries) == 3


def test_summary_is_html_stripped():
    parsed = fetcher.parse_feed(FIXTURE.read_bytes())
    first = parsed.entries[0]
    assert first.summary == "Hello world, this is the first post."
    assert "<" not in first.summary


def test_published_at_is_utc_aware():
    parsed = fetcher.parse_feed(FIXTURE.read_bytes())
    first = parsed.entries[0]
    assert first.published_at.tzinfo == timezone.utc
    assert first.published_at.year == 2026
    assert first.published_at.hour == 14


def test_guid_falls_back_to_link():
    parsed = fetcher.parse_feed(FIXTURE.read_bytes())
    third = parsed.entries[2]
    assert third.guid == "https://example.com/third"


def test_fetch_feed_uses_client(client, feed_url):
    parsed = fetcher.fetch_feed(feed_url, client=client)
    assert parsed.title == "Example Tech Blog"
    assert len(parsed.entries) == 3
