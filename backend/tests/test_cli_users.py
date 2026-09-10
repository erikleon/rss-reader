"""CLI user scoping.

The CLI shares the database with the web app, so once several people use it
every per-person command has to say whose feeds it means. It never guesses:
guessing here would operate on somebody else's queue with no confirmation and
no undo, which is the same failure the service layer's removed default was
about.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from rss_reader import cli, db, service

from conftest import OTHER_LOGIN, OWNER_LOGIN

runner = CliRunner()


@pytest.fixture
def cli_db(file_engine, monkeypatch, session, other_id):
    """Point the CLI at the file-backed engine, with both users present."""
    from sqlmodel import Session

    from rss_reader.models import User

    with Session(file_engine) as s:
        s.add(User(username=OTHER_LOGIN))
        s.commit()
    monkeypatch.setattr(db, "get_engine", lambda: file_engine)
    monkeypatch.setattr(cli, "_ensure_db", lambda: None)
    return file_engine


def _run(args, env=None):
    return runner.invoke(cli.app, args, env=env or {})


def test_a_missing_user_is_an_error_naming_the_valid_ones(cli_db):
    result = _run(["feed", "list"])
    assert result.exit_code == 1
    assert "--user" in result.output
    assert OWNER_LOGIN in result.output


def test_an_unknown_login_is_an_error_naming_the_valid_ones(cli_db):
    result = _run(["feed", "list", "--user", "nobody@example.com"])
    assert result.exit_code == 1
    assert "nobody@example.com" in result.output
    assert OWNER_LOGIN in result.output


def test_the_env_var_stands_in_for_the_flag(cli_db):
    result = _run(["feed", "list"], env={"RSS_READER_CLI_USER": OWNER_LOGIN})
    assert result.exit_code == 0
    assert "No feeds yet" in result.output


def test_a_login_is_matched_case_insensitively(cli_db):
    result = _run(["feed", "list", "--user", OWNER_LOGIN.upper()])
    assert result.exit_code == 0


def test_user_list_shows_every_account(cli_db):
    result = _run(["user", "list"])
    assert result.exit_code == 0
    assert OWNER_LOGIN in result.output
    assert OTHER_LOGIN in result.output


def test_items_are_scoped_to_the_named_user(cli_db, file_engine, client, feed_url, user_id):
    from sqlmodel import Session

    with Session(file_engine) as s:
        service.add_feed(s, feed_url, user_id, client=client)

    # A wide window: the sample feed's items are fixed dates in the past, and
    # the default 30 days would hide them and make this pass for the wrong reason.
    mine = _run(["items", "--days", "36500", "--user", OWNER_LOGIN])
    theirs = _run(["items", "--days", "36500", "--user", OTHER_LOGIN])
    assert mine.exit_code == 0
    assert theirs.exit_code == 0
    assert "No items" in theirs.output
    assert "No items" not in mine.output


def test_refresh_takes_no_user_and_covers_everybody(cli_db):
    """Maintenance, not a per-person action: refreshing one person's feeds from
    a cron entry and leaving everyone else stale is nobody's intent."""
    result = _run(["refresh"])
    assert result.exit_code == 0
    assert "--user" not in result.output


def test_prune_takes_no_user_and_covers_everybody(cli_db):
    result = _run(["prune", "--days", "30"])
    assert result.exit_code == 0
    assert "Pruned" in result.output
