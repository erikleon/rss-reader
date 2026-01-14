"""Tests for OPML parsing and import."""

from __future__ import annotations

import pytest

from rss_reader import opml, service

OPML = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>Subscriptions</title></head>
  <body>
    <outline text="Tech">
      <outline type="rss" text="Example" title="Example Blog"
               xmlUrl="https://example.com/feed.xml"/>
      <outline type="rss" text="Other"
               xmlUrl="https://example.com/other.xml"/>
    </outline>
    <outline type="rss" text="Broken" xmlUrl="https://nope.invalid/feed"/>
  </body>
</opml>
"""


def test_parse_opml_collects_nested_feeds():
    entries = opml.parse_opml(OPML)
    urls = [e.xml_url for e in entries]
    assert urls == [
        "https://example.com/feed.xml",
        "https://example.com/other.xml",
        "https://nope.invalid/feed",
    ]
    assert entries[0].title == "Example Blog"  # title preferred over text


def test_parse_opml_dedupes_repeated_urls():
    doc = (
        '<opml><body>'
        '<outline xmlUrl="https://example.com/feed.xml"/>'
        '<outline xmlUrl="https://example.com/feed.xml"/>'
        "</body></opml>"
    )
    assert len(opml.parse_opml(doc)) == 1


def test_parse_opml_rejects_invalid_xml():
    with pytest.raises(opml.OpmlError):
        opml.parse_opml("not xml <<<")


def test_import_opml_subscribes_and_isolates_failures(session, client):
    result = service.import_opml(session, OPML, client=client)
    assert len(result.added) == 2
    assert len(result.failed) == 1
    assert result.failed[0][0] == "https://nope.invalid/feed"
    assert len(service.list_feeds(session)) == 2


def test_import_opml_skips_already_subscribed(session, client):
    service.add_feed(session, "https://example.com/feed.xml", client=client)
    result = service.import_opml(session, OPML, client=client)
    assert "https://example.com/feed.xml" in result.skipped
    assert len(result.added) == 1  # only the other example feed
    assert len(result.failed) == 1
