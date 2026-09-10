"""Typer CLI. Wraps the same core service functions used by the web API.

Per-person commands take ``--user <login>``, the same Tailscale login string the
web app resolves, so one person is one thing on this box rather than a login in
one place and a row id in another. ``refresh`` and ``prune`` are maintenance and
cover every user instead.

This is data selection, not authentication. Anyone who can run this already has
the database.
"""

from __future__ import annotations

from pathlib import Path

import typer
from sqlmodel import Session, select

from . import auth, config, service
from .db import get_engine, init_db, session_scope
from .models import User

app = typer.Typer(help="A simple personal RSS reader.", no_args_is_help=True)
feed_app = typer.Typer(help="Manage feed subscriptions.", no_args_is_help=True)
user_app = typer.Typer(help="Inspect reader accounts.", no_args_is_help=True)
app.add_typer(feed_app, name="feed")
app.add_typer(user_app, name="user")

USER_OPTION = typer.Option(
    None,
    "--user",
    envvar="RSS_READER_CLI_USER",
    help="Tailscale login to act as. See: rss-reader user list",
)


def _ensure_db() -> None:
    init_db(get_engine())


def _known_logins(session: Session) -> list[str]:
    return [u.username for u in session.exec(select(User).order_by(User.username))]


def _resolve_user(session: Session, login: str | None) -> int:
    """Turn --user (or its env fallback) into a user id, or exit saying why.

    Never falls back to "the first user". Guessing here would silently operate
    on somebody else's feeds, which is the whole reason the service layer lost
    its default.
    """
    known = _known_logins(session)
    if not login:
        typer.secho(
            "No user given. Pass --user <login> or set RSS_READER_CLI_USER.",
            fg=typer.colors.RED,
            err=True,
        )
        _echo_known(known)
        raise typer.Exit(code=1)

    normalized = auth.normalize_login(login)
    user = session.exec(select(User).where(User.username == normalized)).first()
    if user is None:
        typer.secho(f"No reader account for {normalized!r}.", fg=typer.colors.RED, err=True)
        _echo_known(known)
        raise typer.Exit(code=1)
    return user.id


def _echo_known(known: list[str]) -> None:
    if known:
        typer.secho("Known logins: " + ", ".join(known), fg=typer.colors.YELLOW, err=True)
    else:
        typer.secho(
            "No accounts exist yet. One is created the first time somebody opens "
            "the web app through the tailnet.",
            fg=typer.colors.YELLOW,
            err=True,
        )


# --------------------------------------------------------------------------- #
# feed add / remove / list
# --------------------------------------------------------------------------- #
@feed_app.command("add")
def feed_add(url: str, user: str = USER_OPTION) -> None:
    """Subscribe to a feed URL."""
    _ensure_db()
    with session_scope() as session:
        user_id = _resolve_user(session, user)
        try:
            feed = service.add_feed(session, url, user_id)
        except service.FeedError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    typer.secho(f"Added [{feed.id}] {feed.title}", fg=typer.colors.GREEN)


@feed_app.command("remove")
def feed_remove(feed_id: int, user: str = USER_OPTION) -> None:
    """Unsubscribe from a feed by id."""
    _ensure_db()
    with session_scope() as session:
        user_id = _resolve_user(session, user)
        try:
            service.remove_feed(session, feed_id, user_id)
        except service.FeedError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    typer.secho(f"Removed feed {feed_id}", fg=typer.colors.GREEN)


@feed_app.command("list")
def feed_list(user: str = USER_OPTION) -> None:
    """List subscribed feeds."""
    _ensure_db()
    with session_scope() as session:
        feeds = service.list_feeds(session, _resolve_user(session, user))
    if not feeds:
        typer.echo("No feeds yet. Add one with: rss-reader feed add <url>")
        return
    for feed in feeds:
        line = f"[{feed.id}] {feed.title}  ({feed.url})"
        if feed.last_error:
            line += f"  ⚠ {feed.last_error}"
        typer.echo(line)


# --------------------------------------------------------------------------- #
# users
# --------------------------------------------------------------------------- #
@user_app.command("list")
def user_list() -> None:
    """List reader accounts and how many feeds each has."""
    _ensure_db()
    with session_scope() as session:
        users = list(session.exec(select(User).order_by(User.username)))
        counts = {u.id: len(service.list_feeds(session, u.id)) for u in users}
    if not users:
        typer.echo(
            "No accounts yet. One is created the first time somebody opens the "
            "web app through the tailnet."
        )
        return
    for user in users:
        typer.echo(f"[{user.id}] {user.username}  ({counts[user.id]} feed(s))")


# --------------------------------------------------------------------------- #
# import (OPML)
# --------------------------------------------------------------------------- #
@app.command("import")
def import_opml(path: Path, user: str = USER_OPTION) -> None:
    """Import feed subscriptions from an OPML file."""
    _ensure_db()
    try:
        content = path.read_bytes()
    except OSError as exc:
        typer.secho(f"Could not read {path}: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    with session_scope() as session:
        user_id = _resolve_user(session, user)
        try:
            result = service.import_opml(session, content, user_id)
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
    """Pull the latest items from every user's feeds.

    No --user: this is maintenance, and refreshing one person's feeds while
    leaving everybody else stale is not a thing anybody wants from a cron entry.
    """
    _ensure_db()
    with session_scope() as session:
        by_user = service.refresh_all_users(session)
        logins = {u.id: u.username for u in session.exec(select(User))}
    results = [r for rs in by_user.values() for r in rs]
    if not results:
        typer.echo("No feeds to refresh.")
        return
    total = 0
    for user_id, user_results in by_user.items():
        if not user_results:
            continue
        typer.secho(logins.get(user_id, f"user {user_id}"), fg=typer.colors.CYAN, bold=True)
        for r in user_results:
            if r.error:
                typer.secho(f"  {r.title}: error — {r.error}", fg=typer.colors.RED)
            else:
                total += r.new_count
                typer.echo(f"  {r.title}: {r.new_count} new")
    typer.secho(f"Done. {total} new item(s).", fg=typer.colors.GREEN)


# --------------------------------------------------------------------------- #
# items
# --------------------------------------------------------------------------- #
@app.command()
def items(
    days: int = typer.Option(30, help="How many days back to show."),
    unread: bool = typer.Option(False, "--unread", help="Only unread items."),
    user: str = USER_OPTION,
) -> None:
    """List items grouped by day."""
    _ensure_db()
    with session_scope() as session:
        user_id = _resolve_user(session, user)
        rows = service.list_items(session, user_id, days=days, unread_only=unread)
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
def read(item_id: int, user: str = USER_OPTION) -> None:
    """Mark an item as read."""
    _set_read(item_id, True, user)


@app.command()
def unread(item_id: int, user: str = USER_OPTION) -> None:
    """Mark an item as unread."""
    _set_read(item_id, False, user)


def _set_read(item_id: int, value: bool, user: str | None) -> None:
    _ensure_db()
    with session_scope() as session:
        user_id = _resolve_user(session, user)
        try:
            service.set_read(session, item_id, value, user_id)
        except service.FeedError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    typer.secho(f"Item {item_id} marked {'read' if value else 'unread'}.", fg=typer.colors.GREEN)


@app.command("read-all")
def read_all(user: str = USER_OPTION) -> None:
    """Mark every item as read."""
    _ensure_db()
    with session_scope() as session:
        count = service.mark_all_read(session, _resolve_user(session, user))
    typer.secho(f"Marked {count} item(s) read.", fg=typer.colors.GREEN)


# --------------------------------------------------------------------------- #
# prune (retention)
# --------------------------------------------------------------------------- #
@app.command()
def prune(
    days: int = typer.Option(
        None, help="Delete items older than this many days [default: RSS_READER_RETENTION_DAYS]."
    ),
    include_unread: bool = typer.Option(
        False, "--all", help="Also delete unread items (default keeps unread)."
    ),
) -> None:
    """Delete old items from every user's feeds, to keep the database small.

    No --user, for the same reason as refresh: retention is maintenance.
    """
    _ensure_db()
    cutoff_days = days if days is not None else config.RETENTION_DAYS
    if cutoff_days <= 0:
        typer.secho(
            "Specify --days N (or set RSS_READER_RETENTION_DAYS).",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    with session_scope() as session:
        count = service.prune_all_users(
            session, days=cutoff_days, include_unread=include_unread
        )
    typer.secho(f"Pruned {count} item(s).", fg=typer.colors.GREEN)


# --------------------------------------------------------------------------- #
# serve
# --------------------------------------------------------------------------- #
@app.command()
def serve(
    host: str = typer.Option(
        config.HOST,
        "--host",
        envvar="RSS_READER_HOST",
        help="Address to bind. Loopback by default; see the note in config.py.",
    ),
    # env var is a string, so allow passing via env var without needing to convert to int:
    port: int = typer.Option(8000, "--port", envvar="RSS_READER_PORT", help="Port to serve on."),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes."),
) -> None:
    """Run the web app (API + built frontend)."""
    import uvicorn

    _ensure_db()
    typer.echo(f"Serving on http://{host}:{port}")
    uvicorn.run("rss_reader.api:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
