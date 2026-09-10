"""The SSRF guard on outbound feed fetches.

Subscribing to a feed makes the server fetch a URL somebody else chose. On a box
that also runs other services on internal addresses, that is the difference
between a feed reader and a port scanner anyone in the household can drive.

The resolver is injected rather than mocked at the socket layer, so these run
offline and assert on the decision rather than on DNS.
"""

from __future__ import annotations

import httpx
import pytest

from rss_reader import config, fetcher


def _resolver(*addresses):
    def resolve(host, port):
        return list(addresses)

    return resolve


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",  # ollama, pihole admin, the house dashboard
        "::1",
        "10.0.0.5",
        "192.168.1.37",  # the router
        "172.18.0.1",  # the Docker bridge gateway
        "169.254.169.254",  # cloud metadata
        "0.0.0.0",
        "224.0.0.1",  # multicast
        "fc00::1",  # unique local
        "fe80::1",  # link local
    ],
)
def test_internal_addresses_are_refused(address):
    with pytest.raises(fetcher.BlockedUrlError):
        fetcher.check_url_allowed("http://feeds.example.com/x", resolve=_resolver(address))


@pytest.mark.parametrize("address", ["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"])
def test_public_addresses_are_allowed(address):
    fetcher.check_url_allowed("https://feeds.example.com/x", resolve=_resolver(address))


def test_a_name_is_refused_if_any_of_its_addresses_is_internal():
    """A host that resolves to both is still a way in; the public answer would
    pass the check and the internal one would be the connection."""
    with pytest.raises(fetcher.BlockedUrlError):
        fetcher.check_url_allowed(
            "http://split.example.com/x", resolve=_resolver("93.184.216.34", "127.0.0.1")
        )


@pytest.mark.parametrize("url", ["file:///etc/passwd", "gopher://x/1", "ftp://x/y"])
def test_non_http_schemes_are_refused(url):
    with pytest.raises(fetcher.BlockedUrlError):
        fetcher.check_url_allowed(url, resolve=_resolver("93.184.216.34"))


def test_a_name_that_does_not_resolve_is_refused_not_crashed():
    def boom(host, port):
        raise OSError("Name or service not known")

    with pytest.raises(fetcher.BlockedUrlError):
        fetcher.check_url_allowed("http://nope.example/x", resolve=boom)


# --------------------------------------------------------------------------- #
# Redirects and size, through _get
# --------------------------------------------------------------------------- #
def test_a_redirect_to_an_internal_address_is_refused(monkeypatch):
    """The reason redirects are followed by hand. httpx would follow this one
    itself, and then only the URL that was typed ever gets checked."""
    monkeypatch.setattr(config, "FETCH_GUARD", True)
    monkeypatch.setattr(
        fetcher, "check_url_allowed", lambda url, **kw: _guard_public_only(url)
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "public.example.com":
            return httpx.Response(302, headers={"location": "http://127.0.0.1:11434/api/tags"})
        return httpx.Response(200, text="should never be reached")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(fetcher.BlockedUrlError):
        fetcher._get("http://public.example.com/feed", client)


def _guard_public_only(url: str) -> None:
    if "127.0.0.1" in url:
        raise fetcher.BlockedUrlError(f"blocked {url}")


def test_a_redirect_loop_stops(monkeypatch):
    monkeypatch.setattr(config, "FETCH_GUARD", False)
    monkeypatch.setattr(config, "FETCH_MAX_REDIRECTS", 3)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/next"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(fetcher.BlockedUrlError, match="redirects"):
        fetcher._get("http://example.com/feed", client)


def test_an_oversized_body_is_refused(monkeypatch):
    monkeypatch.setattr(config, "FETCH_GUARD", False)
    monkeypatch.setattr(config, "FETCH_MAX_BYTES", 1024)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 4096)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(fetcher.BlockedUrlError, match="exceeds"):
        fetcher._get("http://example.com/feed", client)


def test_a_blocked_url_reads_as_a_feed_error_not_a_crash(session, user_id, monkeypatch):
    """It must surface as a 400 telling the person their URL is not allowed,
    rather than as a 500 that looks like the reader is broken."""
    from rss_reader import service

    monkeypatch.setattr(config, "FETCH_GUARD", True)

    with pytest.raises(service.FeedError):
        service.add_feed(session, "http://localhost:11434/api/tags", user_id)
