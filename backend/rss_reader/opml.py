"""Parse OPML subscription lists into feed URLs.

OPML is the de-facto format readers use to import/export subscriptions. Feeds are
``<outline>`` elements carrying an ``xmlUrl`` attribute, possibly nested in folders.
"""

from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree


class OpmlError(Exception):
    """Raised when OPML content cannot be parsed."""


@dataclass
class OpmlEntry:
    title: str
    xml_url: str


def parse_opml(content: bytes | str) -> list[OpmlEntry]:
    """Return every feed (``outline`` with an ``xmlUrl``) found in the document."""
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise OpmlError(f"Invalid OPML: {exc}") from exc

    entries: list[OpmlEntry] = []
    seen: set[str] = set()
    for outline in root.iter("outline"):
        xml_url = (outline.get("xmlUrl") or "").strip()
        if not xml_url or xml_url in seen:
            continue
        seen.add(xml_url)
        title = (outline.get("title") or outline.get("text") or xml_url).strip()
        entries.append(OpmlEntry(title=title, xml_url=xml_url))
    return entries
