"""Extraction and sanitisation.

The two halves are held to different standards on purpose. Extraction is a
heuristic and the tests say what it should usually do. Sanitisation is a
boundary and the tests say what must never get through, so a failure there is
never "the heuristic drifted".
"""

from __future__ import annotations

import pytest

from rss_reader import extract

BASE = "https://example.com/posts/1"


def page(body: str, head: str = "<title>Site - A Post</title>") -> str:
    return f"<html><head>{head}</head><body>{body}</body></html>"


PROSE = (
    "<p>A paragraph with enough words in it, and commas, to clear the length "
    "floor that stops navigation being mistaken for an article.</p>"
    "<p>A second paragraph, similarly long, so the container it sits in scores "
    "higher than anything else on the page.</p>"
)


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
def test_the_article_wins_over_the_furniture_around_it():
    html = page(
        '<nav><a href="/a">Home</a><a href="/b">About</a></nav>'
        f'<div id="content">{PROSE}</div>'
        '<div class="sidebar"><p>Sidebar text that is long enough, with commas, '
        "to score if class names were not read at all.</p></div>"
        "<footer><p>Footer text, also long enough, with commas, to be a "
        "candidate on length alone.</p></footer>"
    )
    article = extract.extract(html, BASE)
    assert "A paragraph with enough words" in article.text
    assert "Sidebar text" not in article.text
    assert "Footer text" not in article.text


def test_an_article_split_across_containers_is_reassembled():
    """Ars Technica splits a body across sibling containers. Taking only the
    highest-scoring one kept 6 paragraphs of 14: an article that stops
    mid-story, which is worse than no reader view because it looks complete."""
    half = (
        "<p>{} half, long enough to score well past the floor, with commas in "
        "it, and more words after those.</p>"
    )
    html = page(
        f'<div class="post-content">{half.format("First") * 3}</div>'
        '<div class="ad-slot"><p>promo</p></div>'
        f'<div class="post-content">{half.format("Second") * 3}</div>'
    )
    article = extract.extract(html, BASE)
    assert "First half" in article.text
    assert "Second half" in article.text


def test_reassembled_pieces_keep_their_document_order():
    block = "<p>{} paragraph, long enough to score, with commas, and more.</p>"
    html = page(
        f'<div class="post-content">{block.format("Alpha") * 2}</div>'
        f'<div class="post-content">{block.format("Beta") * 3}</div>'
    )
    article = extract.extract(html, BASE)
    # Beta scores higher (more text). Order must still follow the page.
    assert article.text.index("Alpha") < article.text.index("Beta")


def test_nothing_is_rendered_twice_when_pieces_nest():
    inner = f'<div class="post-body">{PROSE}</div>'
    html = page(f'<div class="article-content">{inner}</div>')
    article = extract.extract(html, BASE)
    assert article.html.count("A paragraph with enough words") == 1


def test_a_page_with_no_prose_is_refused():
    with pytest.raises(extract.ExtractionError):
        extract.extract(page("<nav><a href=/a>Home</a></nav>"), BASE)


def test_word_count_counts_words():
    article = extract.extract(page(f'<div id="content">{PROSE}</div>'), BASE)
    assert article.word_count == len(article.text.split())
    assert article.word_count > 20


# --------------------------------------------------------------------------- #
# Titles
# --------------------------------------------------------------------------- #
def test_the_headline_comes_from_the_article_not_the_masthead():
    """A document-wide search for the first h1 finds the site name on any site
    that puts one in a banner, which titled a post "Simon Willison's Weblog"."""
    html = page(
        "<header><h1>Site Name</h1></header>"
        f'<div id="content"><h1>The Real Headline</h1>{PROSE}</div>'
    )
    assert extract.extract(html, BASE).title == "The Real Headline"


def test_a_subheading_is_not_used_as_the_headline():
    """An h2 partway down is a section heading. Using one titled an article
    "Mysterious marks"."""
    html = page(
        f'<div id="content"><h2>Mysterious marks</h2>{PROSE}</div>',
        head="<title>Boy developed toasted skin | Ars Technica</title>",
    )
    assert extract.extract(html, BASE).title == "Boy developed toasted skin"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Headline goes here | Site", "Headline goes here"),
        ("Site - Headline goes here", "Headline goes here"),
        ("Headline – Site", "Headline"),
        ("No separator at all", "No separator at all"),
    ],
)
def test_the_site_name_is_trimmed_off_a_document_title(raw, expected):
    html = page(f'<div id="content">{PROSE}</div>', head=f"<title>{raw}</title>")
    assert extract.extract(html, BASE).title == expected


def test_a_page_with_no_title_anywhere_has_none():
    html = page(f'<div id="content">{PROSE}</div>', head="")
    assert extract.extract(html, BASE).title is None


# --------------------------------------------------------------------------- #
# Sanitisation. Not a heuristic: these must never regress.
# --------------------------------------------------------------------------- #
def _fragment(inner: str) -> str:
    return extract.extract(page(f'<div id="content">{PROSE}{inner}</div>'), BASE).html


@pytest.mark.parametrize(
    "hostile",
    [
        "<script>alert(1)</script>",
        "<style>body{display:none}</style>",
        '<iframe src="https://evil.example"></iframe>',
        "<object data='x'></object>",
        "<embed src='x'>",
        "<form><input name=p><button>go</button></form>",
        "<svg onload=alert(1)></svg>",
        "<noscript>hidden</noscript>",
    ],
)
def test_dangerous_elements_do_not_survive(hostile):
    fragment = _fragment(hostile)
    for tag in ("script", "style", "iframe", "object", "embed", "form", "svg", "noscript"):
        assert f"<{tag}" not in fragment


def test_event_handlers_and_styles_are_dropped():
    fragment = _fragment('<p onclick="steal()" style="color:red" class="x" id="y">t</p>')
    assert "onclick" not in fragment
    assert "style=" not in fragment
    assert "class=" not in fragment
    assert 'id="y"' not in fragment


@pytest.mark.parametrize(
    "scheme",
    ["javascript:alert(1)", "data:text/html,<script>alert(1)</script>", "vbscript:x"],
)
def test_unsafe_url_schemes_are_dropped(scheme):
    fragment = _fragment(f'<p><a href="{scheme}">link</a><img src="{scheme}"></p>')
    assert "javascript:" not in fragment
    assert "data:text/html" not in fragment
    assert "vbscript:" not in fragment


def test_relative_urls_are_resolved_against_the_page():
    """Without this the reader shows broken images on any site using relative
    paths, which is most of them."""
    fragment = _fragment('<p><a href="/other">a</a><img src="img/x.png" alt="i"></p>')
    assert 'href="https://example.com/other"' in fragment
    assert 'src="https://example.com/posts/img/x.png"' in fragment


def test_links_open_away_from_the_reader():
    fragment = _fragment('<p><a href="/other">a</a></p>')
    assert 'target="_blank"' in fragment
    assert 'rel="noreferrer noopener"' in fragment


def test_text_is_escaped_rather_than_passed_through():
    fragment = _fragment("<p>a &lt; b &amp; c</p>")
    assert "&lt;" in fragment
    assert "<script" not in fragment


def test_an_unknown_tag_is_unwrapped_not_deleted():
    """A <div> or a custom element around a paragraph must not take the
    paragraph with it."""
    fragment = _fragment("<custom-thing><p>Kept text inside a strange tag.</p></custom-thing>")
    assert "Kept text inside a strange tag." in fragment
    assert "<custom-thing" not in fragment


def test_malformed_html_does_not_raise():
    """Real pages have unclosed and stray tags. Refusing to parse them means
    refusing to read most of the web."""
    html = page(f'<div id="content"><p>Unclosed paragraph, long enough, with commas'
                f"{PROSE}</span></b></div>")
    assert extract.extract(html, BASE).text
