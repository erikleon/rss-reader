"""Tests for structured refresh logging."""

from __future__ import annotations

import logging

import httpx

from rss_reader import service


def test_refresh_logs_run_summary(session, client, feed_url, caplog):
    service.add_feed(session, feed_url, client=client)
    with caplog.at_level(logging.INFO, logger="rss_reader.service"):
        service.refresh_all(session, client=client)
    messages = [r.getMessage() for r in caplog.records]
    assert any("refresh complete" in m and "feeds=1" in m for m in messages)


def test_refresh_logs_feed_error(session, client, feed_url, caplog):
    service.add_feed(session, feed_url, client=client)
    failing = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    )
    with caplog.at_level(logging.WARNING, logger="rss_reader.service"):
        service.refresh_all(session, client=failing)
    assert any("feed refresh failed" in r.getMessage() for r in caplog.records)
