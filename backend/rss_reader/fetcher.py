"""Fetch a feed over HTTP and normalize its entries.

Kept deliberately free of any database concern so it can be unit-tested against a
local fixture with no network access (see ``parse_feed``).

Every outbound request in this module goes through ``_get``, which is the only
place a URL somebody else chose turns into a socket. Subscribing to a feed makes
the server fetch that URL, so on a host running other services this is the
difference between a feed reader and an internal port scanner. The guard resolves
the hostname and refuses anything that lands on a loopback, private, link-local
or otherwise reserved address, and it runs on every redirect hop rather than only
on the URL that was typed.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import feedparser
import httpx

from . import config

_FEED_TYPES = ("application/rss+xml", "application/atom+xml", "application/xml", "text/xml")

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
    # feedparser's format version (e.g. "rss20", "atom10"); empty when the
    # content is not a recognized feed (used to trigger autodiscovery).
    version: str = ""

    @property
    def is_feed(self) -> bool:
        return bool(self.version) or bool(self.entries)


class FeedDiscoveryError(Exception):
    """Raised when a URL is not a feed and no feed link can be discovered."""


class BlockedUrlError(Exception):
    """Raised when a URL points somewhere this app must not fetch."""


def _resolve(host: str, port: int) -> list[str]:
    """Every address ``host`` resolves to. Separated out so tests can fake it."""
    infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    return [info[4][0] for info in infos]


def check_url_allowed(url: str, *, resolve=_resolve) -> None:
    """Raise ``BlockedUrlError`` unless ``url`` is a public http(s) address.

    The check is on the resolved addresses rather than on the hostname, because
    a name is free to point anywhere and "localhost" is not the only way to
    write 127.0.0.1.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise BlockedUrlError(f"Refusing to fetch a {parts.scheme or 'schemeless'} URL")
    if not parts.hostname:
        raise BlockedUrlError(f"No host in {url}")

    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        addresses = resolve(parts.hostname, port)
    except OSError as exc:
        raise BlockedUrlError(f"Could not resolve {parts.hostname}: {exc}") from exc

    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global or ip.is_multicast:
            raise BlockedUrlError(
                f"Refusing to fetch {parts.hostname}: it resolves to {ip}, "
                "which is on this network rather than the internet"
            )


class _FeedLinkParser(HTMLParser):
    """Collect <link rel="alternate" type="...rss/atom..."> hrefs from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "link":
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        rel = a.get("rel", "").lower()
        type_ = a.get("type", "").lower()
        href = a.get("href")
        if href and "alternate" in rel and type_ in _FEED_TYPES:
            self.links.append(href)


def discover_feed_links(content: bytes | str, base_url: str) -> list[str]:
    """Return absolute feed URLs advertised in an HTML page's <head>."""
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
    parser = _FeedLinkParser()
    parser.feed(content)
    return [urljoin(base_url, href) for href in parser.links]


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
    return ParsedFeed(
        title=title.strip(),
        site_url=site_url,
        entries=entries,
        version=parsed.get("version", "") or "",
    )


def _read_capped(response: httpx.Response) -> bytes:
    """Read a streamed body, refusing one larger than the configured ceiling.

    The count is of decoded bytes, which is the number worth capping: a small
    compressed body that expands to gigabytes is the case a cap exists for.
    """
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > config.FETCH_MAX_BYTES:
            response.close()
            raise BlockedUrlError(
                f"Response from {response.url} exceeds {config.FETCH_MAX_BYTES} bytes"
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _send_once(
    client: httpx.Client, url: str, headers: dict[str, str]
) -> httpx.Response:
    """One request, no redirect following, body read under the size cap."""
    if config.FETCH_GUARD:
        check_url_allowed(url)
    request = client.build_request("GET", url, headers=headers)
    streamed = client.send(request, stream=True, follow_redirects=False)
    try:
        body = b"" if streamed.status_code == 304 else _read_capped(streamed)
    finally:
        streamed.close()

    # Rebuild as a normal response so callers keep using .content and .url.
    #
    # The encoding headers must not come with it. iter_bytes() hands back bytes
    # httpx has already decompressed, so a Content-Encoding of gzip on the new
    # response tells httpx to decompress them a second time, and the second
    # attempt fails on the first byte: "Error -3 while decompressing data:
    # incorrect header check". Content-Length is dropped for the same reason,
    # since it describes the compressed body rather than this one.
    #
    # Most feeds gzip and some do not, so leaving these on breaks the majority
    # of real sites while the offline tests, whose transport compresses
    # nothing, stay green.
    passthrough = httpx.Headers(streamed.headers)
    for header in ("content-encoding", "content-length", "transfer-encoding"):
        if header in passthrough:
            del passthrough[header]

    return httpx.Response(
        status_code=streamed.status_code,
        headers=passthrough,
        content=body,
        request=request,
    )


def _get(
    url: str,
    client: httpx.Client | None,
    extra_headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Fetch ``url``, following redirects by hand so every hop is checked.

    httpx would follow them for us, but then only the first URL passes the
    guard and a 302 to 127.0.0.1 goes straight through.
    """
    headers = {"User-Agent": config.USER_AGENT}
    if extra_headers:
        headers.update(extra_headers)

    owned = client is None
    client = client or httpx.Client(timeout=config.FETCH_TIMEOUT)
    try:
        current = url
        for _ in range(config.FETCH_MAX_REDIRECTS + 1):
            response = _send_once(client, current, headers)
            location = response.headers.get("location")
            if not response.is_redirect or not location:
                # 304 (Not Modified) is a successful conditional response.
                if response.status_code != 304:
                    response.raise_for_status()
                return response
            current = str(httpx.URL(current).join(location))
        raise BlockedUrlError(
            f"More than {config.FETCH_MAX_REDIRECTS} redirects starting at {url}"
        )
    finally:
        if owned:
            client.close()


def fetch_feed(url: str, *, client: httpx.Client | None = None) -> ParsedFeed:
    """Fetch ``url`` and return the parsed feed. Raises on network/HTTP errors."""
    return parse_feed(_get(url, client).content)


@dataclass
class FetchResult:
    not_modified: bool
    parsed: ParsedFeed | None
    etag: str | None
    last_modified: str | None


def fetch_conditional(
    url: str,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
    client: httpx.Client | None = None,
) -> FetchResult:
    """Fetch ``url`` sending validators; report 304 without re-parsing.

    Returns the new ETag/Last-Modified from the response so the caller can store
    them for next time.
    """
    headers: dict[str, str] = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    response = _get(url, client, headers)
    if response.status_code == 304:
        return FetchResult(True, None, etag, last_modified)
    return FetchResult(
        not_modified=False,
        parsed=parse_feed(response.content),
        etag=response.headers.get("etag"),
        last_modified=response.headers.get("last-modified"),
    )


def fetch_feed_autodiscover(
    url: str, *, client: httpx.Client | None = None
) -> tuple[str, ParsedFeed]:
    """Fetch ``url``; if it is an HTML page, discover and fetch its feed.

    Returns the ``(resolved_url, ParsedFeed)`` actually used so the caller can
    store the real feed URL. Raises ``FeedDiscoveryError`` if nothing is found.
    """
    response = _get(url, client)
    parsed = parse_feed(response.content)
    if parsed.is_feed:
        return str(response.url), parsed

    links = discover_feed_links(response.content, str(response.url))
    for link in links:
        candidate = parse_feed(_get(link, client).content)
        if candidate.is_feed:
            return link, candidate
    raise FeedDiscoveryError(f"No RSS/Atom feed found at {url}")
