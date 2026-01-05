"""Fetch a feed over HTTP and normalize its entries.

Kept deliberately free of any database concern so it can be unit-tested against a
local fixture with no network access (see ``parse_feed``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape

import feedparser
import httpx

from . import config

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass
class ParsedEntry:
    guid: str
    title: str
    link: str | None
    summary: str | None
    published_at: datetime


@dataclass
class ParsedFeed:
    title: str
    site_url: str | None
    entries: list[ParsedEntry] = field(default_factory=list)


def _clean_summary(raw: str | None) -> str | None:
    """Strip HTML tags/entities and collapse whitespace, then truncate."""
    if not raw:
        return None
    text = unescape(_TAG_RE.sub("", raw))
    text = _WS_RE.sub(" ", text).strip()
    if not text:
        return None
    if len(text) > config.SNIPPET_LENGTH:
        text = text[: config.SNIPPET_LENGTH].rstrip() + "…"
    return text


def _entry_published(entry) -> datetime:
    """Best-effort published time as timezone-aware UTC; fall back to now."""
    for key in ("published_parsed", "updated_parsed"):
        struct = entry.get(key)
        if struct:
            return datetime(*struct[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def parse_feed(content: bytes | str) -> ParsedFeed:
    """Parse raw feed bytes/text into a normalized ``ParsedFeed``."""
    parsed = feedparser.parse(content)
    feed_meta = parsed.get("feed", {})
    title = feed_meta.get("title") or feed_meta.get("link") or "Untitled feed"
    site_url = feed_meta.get("link")

    entries: list[ParsedEntry] = []
    for entry in parsed.entries:
        link = entry.get("link")
        guid = entry.get("id") or link
        if not guid:
            # Nothing stable to dedupe on; skip rather than create duplicates.
            continue
        summary = entry.get("summary")
        if summary is None and entry.get("content"):
            summary = entry["content"][0].get("value")
        entries.append(
            ParsedEntry(
                guid=guid,
                title=(entry.get("title") or "(untitled)").strip(),
                link=link,
                summary=_clean_summary(summary),
                published_at=_entry_published(entry),
            )
        )
    return ParsedFeed(title=title.strip(), site_url=site_url, entries=entries)


def fetch_feed(url: str, *, client: httpx.Client | None = None) -> ParsedFeed:
    """Fetch ``url`` and return the parsed feed. Raises on network/HTTP errors."""
    headers = {"User-Agent": config.USER_AGENT}
    if client is not None:
        response = client.get(url, headers=headers, follow_redirects=True)
    else:
        response = httpx.get(
            url,
            headers=headers,
            follow_redirects=True,
            timeout=config.FETCH_TIMEOUT,
        )
    response.raise_for_status()
    return parse_feed(response.content)
