"""The reader view end to end: fetching, caching, ownership and retention."""

from __future__ import annotations

import httpx
import pytest
from sqlmodel import Session, select

from rss_reader import config, service
from rss_reader.models import Article, Item

ARTICLE_HTML = (
    "<html><head><title>A Post | Site</title></head><body>"
    "<nav><a href='/x'>nav</a></nav>"
    "<div id='content'><h1>The Headline</h1>"
    "<p>A paragraph with enough words in it, and commas, to clear the floor.</p>"
    "<p>A second paragraph, also long enough, with commas, to score well.</p>"
    "<script>alert(1)</script>"
    "</div></body></html>"
)


@pytest.fixture
def pages():
    """Serves an article page, and some things that are not one."""
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        path = request.url.path
        if path == "/dead":
            return httpx.Response(404, text="gone")
        if path == "/pdf":
            return httpx.Response(200, content=b"%PDF-1.4", headers={"content-type": "application/pdf"})
        if path == "/empty":
            return httpx.Response(200, text="<html><body><nav>nothing</nav></body></html>",
                                  headers={"content-type": "text/html"})
        return httpx.Response(200, text=ARTICLE_HTML, headers={"content-type": "text/html"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    client.calls = calls  # type: ignore[attr-defined]
    with client:
        yield client


@pytest.fixture
def item(session, client, feed_url, user_id) -> Item:
    feed = service.add_feed(session, feed_url, user_id, client=client)
    row = session.exec(select(Item).where(Item.feed_id == feed.id)).first()
    row.link = "https://example.com/story"
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #
def test_the_article_is_fetched_and_stored(session, item, user_id, pages):
    article = service.get_article(session, item.id, user_id, client=pages)
    assert article.error is None
    assert article.title == "The Headline"
    assert "A paragraph with enough words" in article.html
    assert "<script" not in article.html
    assert article.word_count > 10


def test_opening_it_again_does_not_refetch(session, item, user_id, pages):
    service.get_article(session, item.id, user_id, client=pages)
    before = pages.calls["count"]
    service.get_article(session, item.id, user_id, client=pages)
    assert pages.calls["count"] == before


def test_refresh_refetches(session, item, user_id, pages):
    service.get_article(session, item.id, user_id, client=pages)
    before = pages.calls["count"]
    service.get_article(session, item.id, user_id, refresh=True, client=pages)
    assert pages.calls["count"] > before


def test_a_changed_link_refetches(session, item, user_id, pages):
    """The cache is keyed by item, so a link that changed under it must not
    keep serving the old page."""
    service.get_article(session, item.id, user_id, client=pages)
    before = pages.calls["count"]
    item.link = "https://example.com/moved"
    session.add(item)
    session.commit()
    service.get_article(session, item.id, user_id, client=pages)
    assert pages.calls["count"] > before


# --------------------------------------------------------------------------- #
# Failure is data, not an exception
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path,reason", [("/dead", "404"), ("/pdf", "pdf"), ("/empty", "article")])
def test_an_unreadable_page_is_recorded_rather_than_raised(
    session, item, user_id, pages, path, reason
):
    item.link = f"https://example.com{path}"
    session.add(item)
    session.commit()

    article = service.get_article(session, item.id, user_id, client=pages)

    assert article.html is None
    assert article.error
    assert reason.lower() in article.error.lower()


def test_a_failure_is_cached_too(session, item, user_id, pages):
    """A page that cannot be read is a property of the page. Re-fetching on
    every open is a slow way to get the same answer."""
    item.link = "https://example.com/dead"
    session.add(item)
    session.commit()
    service.get_article(session, item.id, user_id, client=pages)
    before = pages.calls["count"]
    service.get_article(session, item.id, user_id, client=pages)
    assert pages.calls["count"] == before


def test_an_item_with_no_link_is_a_user_error(session, item, user_id, pages):
    item.link = None
    session.add(item)
    session.commit()
    with pytest.raises(service.FeedError, match="no link"):
        service.get_article(session, item.id, user_id, client=pages)


def test_the_ssrf_guard_still_applies(session, item, user_id, monkeypatch):
    """The reader fetches a URL a feed chose rather than one a person typed,
    so the guard matters more here than anywhere else."""
    monkeypatch.setattr(config, "FETCH_GUARD", True)
    item.link = "http://127.0.0.1:11434/api/tags"
    session.add(item)
    session.commit()

    article = service.get_article(session, item.id, user_id)

    assert article.html is None
    assert "this network" in article.error


# --------------------------------------------------------------------------- #
# Ownership
# --------------------------------------------------------------------------- #
def test_another_user_cannot_read_your_article(session, item, other_id, pages):
    with pytest.raises(service.FeedError, match="not found"):
        service.get_article(session, item.id, other_id, client=pages)


def test_a_missing_item_and_someone_elses_look_the_same(session, item, other_id, pages):
    """Telling somebody an id exists but is not theirs is a way to enumerate
    other people's items."""
    with pytest.raises(service.FeedError) as theirs:
        service.get_article(session, item.id, other_id, client=pages)
    with pytest.raises(service.FeedError) as missing:
        service.get_article(session, 999_999, other_id, client=pages)
    assert "not found" in str(theirs.value)
    assert "not found" in str(missing.value)


# --------------------------------------------------------------------------- #
# Retention. Cached bodies are the largest rows in the database.
# --------------------------------------------------------------------------- #
def test_removing_a_feed_takes_the_cached_articles(file_engine, client, feed_url, user_id, pages):
    with Session(file_engine) as session:
        feed = service.add_feed(session, feed_url, user_id, client=client)
        row = session.exec(select(Item).where(Item.feed_id == feed.id)).first()
        row.link = "https://example.com/story"
        session.add(row)
        session.commit()
        service.get_article(session, row.id, user_id, client=pages)
        assert session.exec(select(Article)).all()

        service.remove_feed(session, feed.id, user_id)

        assert session.exec(select(Article)).all() == []


def test_pruning_items_takes_the_cached_articles(file_engine, client, feed_url, user_id, pages):
    from datetime import datetime, timedelta, timezone

    with Session(file_engine) as session:
        feed = service.add_feed(session, feed_url, user_id, client=client)
        row = session.exec(select(Item).where(Item.feed_id == feed.id)).first()
        row.link = "https://example.com/story"
        row.read = True
        row.published_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=400)
        session.add(row)
        session.commit()
        service.get_article(session, row.id, user_id, client=pages)
        assert session.exec(select(Article)).all()

        assert service.prune_items(session, user_id, days=30) >= 1

        assert session.exec(select(Article)).all() == []
