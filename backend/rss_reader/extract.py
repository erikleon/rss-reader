"""Turn a fetched article page into a small, safe fragment of HTML.

Two jobs that are easy to confuse, kept apart on purpose:

**Extraction** decides which part of the page is the article. It is a heuristic
and it is allowed to be wrong; the worst case is a reader view that shows the
wrong column, and the original is one click away.

**Sanitisation** decides what may survive into the page we render. It is not a
heuristic and it is not allowed to be wrong. Feeds and the pages they link to
are written by strangers, so the rule is an allowlist of tags and attributes,
never a list of things to strip. Anything not named here does not get through,
which means a tag nobody thought of is dropped rather than passed.

No third-party parser. The standard library's HTMLParser already builds the
autodiscovery scanner in fetcher.py, and a reader view is not a reason to put a
C extension in the image.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape, unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

# --------------------------------------------------------------------------- #
# What may survive into the rendered page
# --------------------------------------------------------------------------- #
# Structure, emphasis, lists, quotes, code, tables, figures. No media, no
# embeds, no forms: this is a reading view, and the things left out are the
# things that make a page something other than reading.
ALLOWED_TAGS = frozenset(
    """
    p br hr h1 h2 h3 h4 h5 h6
    ul ol li dl dt dd
    blockquote q cite
    pre code kbd samp var
    em strong b i u s small mark sup sub abbr time
    a img figure figcaption
    table thead tbody tfoot tr th td caption colgroup col
    article section div span
    """.split()
)

# Per-tag attribute allowlist. Everything else goes, including every class,
# id, style and on* handler, so no inline script and no author stylesheet.
ALLOWED_ATTRS: dict[str, frozenset[str]] = {
    "a": frozenset({"href", "title"}),
    "img": frozenset({"src", "alt", "title", "width", "height"}),
    "time": frozenset({"datetime"}),
    "abbr": frozenset({"title"}),
    "td": frozenset({"colspan", "rowspan"}),
    "th": frozenset({"colspan", "rowspan", "scope"}),
    "col": frozenset({"span"}),
    "colgroup": frozenset({"span"}),
}

# Dropped with everything inside them. Distinct from "not allowed": an
# unallowed tag keeps its children, because a <div class=x> wrapper around a
# paragraph should not take the paragraph with it.
DISCARD_WITH_CONTENT = frozenset(
    {
        "script", "style", "noscript", "template", "iframe", "object", "embed",
        "applet", "form", "input", "button", "select", "textarea", "label",
        "svg", "canvas", "map", "audio", "video", "source", "track", "picture",
        "nav", "aside", "menu", "dialog",
    }
)

# header and footer are only furniture at the top of a page. Inside an <article>
# they usually hold the headline and the byline, which is exactly what a reader
# view wants, so they are dropped by position rather than by name. Discarding
# them outright cost every extracted article its title.
POSITIONAL_DISCARD = frozenset({"header", "footer"})

# <head> is NOT discarded. Its useful child is <title>, and dropping the whole
# subtree meant the title handler below never ran. Everything else in there is
# either discarded by name (script, style) or absent from ALLOWED_TAGS, so it
# renders as nothing anyway.

VOID_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
     "meta", "param", "source", "track", "wbr"}
)

# Only these schemes may appear in an href or src. A relative URL is resolved
# against the article's own address first, so what is checked here is always
# absolute.
SAFE_SCHEMES = frozenset({"http", "https", "mailto"})

# Class and id fragments that argue for or against a block being the article.
# Lifted from the shape of the original readability heuristic; the point is the
# direction of the signal, not the exact vocabulary.
NEGATIVE = re.compile(
    r"comment|disqus|sidebar|footer|foot|header|masthead|nav|menu|promo|"
    r"advert|\bad\b|ads\b|sponsor|share|social|related|recommend|newsletter|"
    r"subscribe|signup|popup|modal|banner|cookie|consent|breadcrumb|pagination|"
    r"widget|meta\b|tags?\b|byline|caption|hidden",
    re.I,
)
POSITIVE = re.compile(
    r"article|body|content|entry|main|page|post|story|text|blog|column",
    re.I,
)

_WS = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES = re.compile(r"\n{3,}")


class ExtractionError(Exception):
    """Raised when a page yields nothing worth reading."""


# --------------------------------------------------------------------------- #
# A very small DOM
# --------------------------------------------------------------------------- #
@dataclass
class Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["Node | str"] = field(default_factory=list)
    parent: "Node | None" = None
    # Position in the source. Pieces of a split article are reassembled in this
    # order, because the order they scored in says nothing about how to read them.
    order: int = 0

    def text(self) -> str:
        parts: list[str] = []
        for child in self.children:
            parts.append(child if isinstance(child, str) else child.text())
        return "".join(parts)

    def find_all(self, *tags: str) -> list["Node"]:
        found: list[Node] = []
        for child in self.children:
            if isinstance(child, Node):
                if child.tag in tags:
                    found.append(child)
                found.extend(child.find_all(*tags))
        return found

    @property
    def signature(self) -> str:
        """class and id together, which is what the heuristics read."""
        return f"{self.attrs.get('class', '')} {self.attrs.get('id', '')}"


class _TreeBuilder(HTMLParser):
    """Build a Node tree, dropping the subtrees that are never article text.

    Deliberately forgiving. Real pages have unclosed tags and stray closing
    ones, and refusing to parse them would mean refusing to read most of the
    web. An end tag with no matching open tag is ignored rather than treated as
    an error.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("[document]")
        self._stack: list[Node] = [self.root]
        # Depth inside a discarded subtree. Non-zero means throw everything away.
        self._discarding = 0
        self._discard_tag: str | None = None
        self.title: str | None = None
        self._in_title = False
        self._counter = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if self._discarding:
            if tag == self._discard_tag and tag not in VOID_TAGS:
                self._discarding += 1
            return
        if tag in DISCARD_WITH_CONTENT or (
            tag in POSITIONAL_DISCARD and not self._inside_article()
        ):
            self._discarding = 1
            self._discard_tag = tag
            return
        if tag == "title":
            self._in_title = True
            return

        self._counter += 1
        node = Node(
            tag,
            {k.lower(): (v or "") for k, v in attrs},
            parent=self._stack[-1],
            order=self._counter,
        )
        self._stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self._stack.append(node)

    def _inside_article(self) -> bool:
        """Whether the parser is currently within an article-ish container."""
        return any(
            node.tag == "article" or POSITIVE.search(node.signature)
            for node in self._stack
        )

    def handle_startendtag(self, tag: str, attrs) -> None:
        if self._discarding or tag in DISCARD_WITH_CONTENT:
            return
        node = Node(tag, {k.lower(): (v or "") for k, v in attrs}, parent=self._stack[-1])
        self._stack[-1].children.append(node)

    def handle_endtag(self, tag: str) -> None:
        if self._discarding:
            if tag == self._discard_tag:
                self._discarding -= 1
                if self._discarding == 0:
                    self._discard_tag = None
            return
        if tag == "title":
            self._in_title = False
            return
        for depth in range(len(self._stack) - 1, 0, -1):
            if self._stack[depth].tag == tag:
                del self._stack[depth:]
                return
        # No matching open tag. Ignore it rather than unwinding the document.

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title = (self.title or "") + data
            return
        if self._discarding or not data.strip():
            # Whitespace between blocks is not content, and keeping it makes
            # every text length comparison below noisier.
            if data.strip() or not self._stack[-1].children:
                return
            return
        self._stack[-1].children.append(data)


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
def _score_for(node: Node) -> float:
    """How much this block argues for being part of the article."""
    body = node.text().strip()
    if len(body) < 25:
        return 0.0
    score = 1.0
    score += body.count(",")
    score += min(len(body) / 100.0, 3.0)
    return score


def _class_bonus(node: Node) -> float:
    signature = node.signature
    bonus = 0.0
    if NEGATIVE.search(signature):
        bonus -= 25.0
    if POSITIVE.search(signature):
        bonus += 25.0
    if node.tag == "article":
        bonus += 30.0
    return bonus


def find_article(root: Node) -> tuple[Node, dict[int, tuple[Node, float]]]:
    """The subtree most likely to be the article, and every candidate's score.

    Paragraph-driven, like the original readability: score each block of prose,
    give the score to its parent and half to its grandparent, then take the
    best container. A page's article is wherever its paragraphs cluster.

    The scores come back because the winner is usually not the whole article.
    See _assemble.
    """
    candidates: dict[int, tuple[Node, float]] = {}

    for block in root.find_all("p", "pre", "blockquote"):
        score = _score_for(block)
        if not score:
            continue
        parent = block.parent
        if parent is None:
            continue
        for depth, ancestor in enumerate((parent, parent.parent)):
            if ancestor is None or ancestor.tag == "[document]":
                continue
            share = score if depth == 0 else score / 2
            key = id(ancestor)
            current = candidates.get(key, (ancestor, _class_bonus(ancestor)))[1]
            candidates[key] = (ancestor, current + share)

    if not candidates:
        raise ExtractionError("No article text found on the page")

    best, score = max(candidates.values(), key=lambda pair: pair[1])
    if score <= 0:
        raise ExtractionError("No article text found on the page")
    return best, candidates


def _contains(outer: Node, inner: Node) -> bool:
    node: Node | None = inner
    while node is not None:
        if node is outer:
            return True
        node = node.parent
    return False


def _assemble(best: Node, candidates: dict[int, tuple[Node, float]]) -> Node:
    """Gather the winner's worthwhile siblings alongside it.

    The highest-scoring container is usually one part of the article rather
    than all of it. Ars Technica splits a body across sibling divs, and taking
    the winner alone kept six paragraphs out of fourteen: an article that stops
    mid-story, which is worse than not offering a reader view at all because it
    looks complete.

    Sibling inclusion is safe here in a way it would not be in a general
    readability implementation, because nav, header, footer and aside were
    already dropped with their contents while parsing. What is left beside the
    winner is prose or nothing.
    """
    best_score = candidates.get(id(best), (best, 0.0))[1]
    threshold = max(10.0, best_score * 0.25)

    kept: list[Node] = [best]
    for node, score in sorted(candidates.values(), key=lambda pair: -pair[1]):
        if node is best or score < threshold:
            continue
        # Skip anything that overlaps a piece already taken, in either
        # direction. Keeping both a container and its child would render the
        # same paragraphs twice.
        if any(_contains(k, node) or _contains(node, k) for k in kept):
            continue
        kept.append(node)

    if len(kept) == 1:
        return best

    kept.sort(key=lambda node: node.order)
    container = Node("div")
    container.children = list(kept)
    for child in kept:
        child.parent = container
    return container


def _strip_junk(node: Node) -> None:
    """Drop children that look like furniture rather than prose.

    Runs on the chosen subtree only. A link-dense block inside an article is a
    related-stories rail or a share bar; a paragraph is not.
    """
    keep: list[Node | str] = []
    for child in node.children:
        if isinstance(child, str):
            keep.append(child)
            continue
        if child.tag in ("div", "section", "ul", "ol", "aside") and NEGATIVE.search(
            child.signature
        ):
            continue
        text = child.text().strip()
        if child.tag in ("div", "section", "ul", "ol"):
            link_text = sum(len(a.text()) for a in child.find_all("a"))
            if text and link_text / max(len(text), 1) > 0.6 and len(text) < 400:
                continue
        _strip_junk(child)
        keep.append(child)
    node.children = keep


# --------------------------------------------------------------------------- #
# Sanitisation
# --------------------------------------------------------------------------- #
def _safe_url(value: str, base_url: str) -> str | None:
    absolute = urljoin(base_url, value.strip())
    scheme = urlsplit(absolute).scheme.lower()
    if scheme not in SAFE_SCHEMES:
        return None
    return absolute


def _render(node: Node | str, base_url: str, out: list[str]) -> None:
    if isinstance(node, str):
        out.append(escape(node, quote=False))
        return

    tag = node.tag
    if tag not in ALLOWED_TAGS:
        # Unknown wrapper: keep what is inside it. Dropping the children with
        # it would take the article out along with a stray <div>.
        for child in node.children:
            _render(child, base_url, out)
        return

    attrs: list[str] = []
    permitted = ALLOWED_ATTRS.get(tag, frozenset())
    for name, value in node.attrs.items():
        if name not in permitted:
            continue
        if name in ("href", "src"):
            resolved = _safe_url(value, base_url)
            if resolved is None:
                continue
            value = resolved
        attrs.append(f' {name}="{escape(value, quote=True)}"')

    if tag == "a":
        # Every link leaves the reader, so every link opens away from it and
        # gets no handle on the page it came from.
        attrs.append(' target="_blank" rel="noreferrer noopener"')

    if tag in VOID_TAGS:
        out.append(f"<{tag}{''.join(attrs)}>")
        return

    out.append(f"<{tag}{''.join(attrs)}>")
    for child in node.children:
        _render(child, base_url, out)
    out.append(f"</{tag}>")


def sanitize(node: Node, base_url: str) -> str:
    out: list[str] = []
    for child in node.children:
        _render(child, base_url, out)
    return "".join(out)


# --------------------------------------------------------------------------- #
# The whole job
# --------------------------------------------------------------------------- #
@dataclass
class Article:
    title: str | None
    html: str
    text: str
    word_count: int


def _plain_text(node: Node) -> str:
    text = _WS.sub(" ", unescape(node.text()))
    return _BLANK_LINES.sub("\n\n", text).strip()


# A <title> is usually "Headline | Site Name" or "Site Name - Headline". The
# separator is the only reliable part, so take the longest side and let a title
# without one through unchanged.
_TITLE_SPLIT = re.compile(r"\s+[|\u2013\u2014\u00b7-]\s+")


def _title_for(body: Node, document_title: str | None) -> str | None:
    """The article's own headline, preferring one found inside the article.

    A document-wide search for the first h1 finds the site's masthead on any
    site that puts its name in one, which is how the reader ended up titling a
    post "Simon Willison's Weblog".
    """
    for heading in body.find_all("h1"):
        text = _WS.sub(" ", heading.text()).strip()
        if text:
            return text
    # No h1 inside the article. Fall through to <title> rather than settling for
    # an h2: those are section headings partway down the piece, and using one
    # titles the article "Mysterious marks".

    title = _WS.sub(" ", (document_title or "")).strip()
    if not title:
        return None
    parts = [part for part in _TITLE_SPLIT.split(title) if part.strip()]
    return max(parts, key=len).strip() if len(parts) > 1 else title


def extract(html: bytes | str, base_url: str) -> Article:
    """Parse ``html`` and return the readable part of it.

    ``base_url`` is the address the page was fetched from, and every relative
    link and image is resolved against it. Without that a reader view shows
    broken images on any site that uses relative paths, which is most of them.
    """
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")

    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()

    body, candidates = find_article(builder.root)
    body = _assemble(body, candidates)
    _strip_junk(body)

    fragment = sanitize(body, base_url)
    text = _plain_text(body)
    if not text:
        raise ExtractionError("The page's article area held no text")

    title = _title_for(body, builder.title)

    return Article(
        title=title,
        html=fragment,
        text=text,
        word_count=len(text.split()),
    )
