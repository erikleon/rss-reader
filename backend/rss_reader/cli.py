"""Typer CLI. Wraps the same core service functions used by the web API."""

from __future__ import annotations

from pathlib import Path

import typer

from . import service
from .db import get_engine, init_db, session_scope

app = typer.Typer(help="A simple personal RSS reader.", no_args_is_help=True)
feed_app = typer.Typer(help="Manage feed subscriptions.", no_args_is_help=True)
app.add_typer(feed_app, name="feed")


def _ensure_db() -> None:
    init_db(get_engine())


# --------------------------------------------------------------------------- #
# feed add / remove / list
# --------------------------------------------------------------------------- #
@feed_app.command("add")
def feed_add(url: str) -> None:
    """Subscribe to a feed URL."""
    _ensure_db()
    with session_scope() as session:
        try:
            feed = service.add_feed(session, url)
        except service.FeedError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    typer.secho(f"Added [{feed.id}] {feed.title}", fg=typer.colors.GREEN)


@feed_app.command("remove")
def feed_remove(feed_id: int) -> None:
    """Unsubscribe from a feed by id."""
    _ensure_db()
    with session_scope() as session:
        try:
            service.remove_feed(session, feed_id)
        except service.FeedError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    typer.secho(f"Removed feed {feed_id}", fg=typer.colors.GREEN)


@feed_app.command("list")
def feed_list() -> None:
    """List subscribed feeds."""
    _ensure_db()
    with session_scope() as session:
        feeds = service.list_feeds(session)
    if not feeds:
        typer.echo("No feeds yet. Add one with: rss-reader feed add <url>")
        return
    for feed in feeds:
        line = f"[{feed.id}] {feed.title}  ({feed.url})"
        if feed.last_error:
            line += f"  ⚠ {feed.last_error}"
        typer.echo(line)


# --------------------------------------------------------------------------- #
# import (OPML)
# --------------------------------------------------------------------------- #
@app.command("import")
def import_opml(path: Path) -> None:
    """Import feed subscriptions from an OPML file."""
    _ensure_db()
    try:
        content = path.read_bytes()
    except OSError as exc:
        typer.secho(f"Could not read {path}: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    with session_scope() as session:
        try:
            result = service.import_opml(session, content)
        except service.opml.OpmlError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    typer.secho(
        f"Added {len(result.added)}, skipped {len(result.skipped)} (duplicate), "
        f"failed {len(result.failed)}.",
        fg=typer.colors.GREEN,
    )
    for url, err in result.failed:
        typer.secho(f"  ✗ {url}: {err}", fg=typer.colors.RED)


# --------------------------------------------------------------------------- #
# refresh
# --------------------------------------------------------------------------- #
@app.command()
def refresh() -> None:
    """Pull the latest items from all subscribed feeds."""
    _ensure_db()
    with session_scope() as session:
        results = service.refresh_all(session)
    if not results:
        typer.echo("No feeds to refresh.")
        return
    total = 0
    for r in results:
        if r.error:
            typer.secho(f"{r.title}: error — {r.error}", fg=typer.colors.RED)
        else:
            total += r.new_count
            typer.echo(f"{r.title}: {r.new_count} new")
    typer.secho(f"Done. {total} new item(s).", fg=typer.colors.GREEN)


# --------------------------------------------------------------------------- #
# items
# --------------------------------------------------------------------------- #
@app.command()
def items(
    days: int = typer.Option(30, help="How many days back to show."),
    unread: bool = typer.Option(False, "--unread", help="Only unread items."),
) -> None:
    """List items grouped by day."""
    _ensure_db()
    with session_scope() as session:
        rows = service.list_items(session, days=days, unread_only=unread)
        groups = service.group_by_day(rows)
    if not groups:
        typer.echo("No items. Try: rss-reader refresh")
        return
    for group in groups:
        typer.secho(group.day.strftime("%A, %B %d, %Y"), fg=typer.colors.CYAN, bold=True)
        for item in group.items:
            mark = " " if item.read else "•"
            time = item.published_at.strftime("%H:%M")
            typer.echo(f"  {mark} [{item.id}] {time}  {item.title}")
            if item.link:
                typer.secho(f"        {item.link}", fg=typer.colors.BRIGHT_BLACK)
        typer.echo("")


# --------------------------------------------------------------------------- #
# read / unread / read-all
# --------------------------------------------------------------------------- #
@app.command()
def read(item_id: int) -> None:
    """Mark an item as read."""
    _set_read(item_id, True)


@app.command()
def unread(item_id: int) -> None:
    """Mark an item as unread."""
    _set_read(item_id, False)


def _set_read(item_id: int, value: bool) -> None:
    _ensure_db()
    with session_scope() as session:
        try:
            service.set_read(session, item_id, value)
        except service.FeedError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    typer.secho(f"Item {item_id} marked {'read' if value else 'unread'}.", fg=typer.colors.GREEN)


@app.command("read-all")
def read_all() -> None:
    """Mark every item as read."""
    _ensure_db()
    with session_scope() as session:
        count = service.mark_all_read(session)
    typer.secho(f"Marked {count} item(s) read.", fg=typer.colors.GREEN)


# --------------------------------------------------------------------------- #
# serve
# --------------------------------------------------------------------------- #
@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes."),
) -> None:
    """Run the web app (API + built frontend)."""
    import uvicorn

    _ensure_db()
    typer.echo(f"Serving on http://{host}:{port}")
    uvicorn.run("rss_reader.api:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
