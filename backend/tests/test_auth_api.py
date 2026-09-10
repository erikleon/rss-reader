"""Request-level tests for identity, CSRF and cross-user isolation.

These drive the real app through TestClient rather than calling the service
layer, because the guarantees here only exist as HTTP responses. A refusal is a
status code: you cannot assert one by calling a function.

The endpoint list is parametrised on purpose. An endpoint added later without
the identity dependency fails these tests rather than quietly serving one
person's feeds to everybody, which is the failure this whole change exists to
prevent.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from rss_reader import config, service
from rss_reader.api import app
from rss_reader.db import get_session

from conftest import OTHER_LOGIN, OWNER_LOGIN

CSRF = {config.CSRF_HEADER: "1"}

# Every route under /api, so the parametrised refusals below cover all of them.
ENDPOINTS = [
    ("GET", "/api/feeds", None),
    ("POST", "/api/feeds", {"url": "https://example.com/feed.xml"}),
    ("DELETE", "/api/feeds/1", None),
    ("POST", "/api/refresh", None),
    ("GET", "/api/items", None),
    ("POST", "/api/items/1/read", {"read": True}),
    ("POST", "/api/items/read-all", None),
    ("GET", "/api/unread", None),
    ("GET", "/api/me", None),
    ("POST", "/api/import/opml", None),
]

UNSAFE_ENDPOINTS = [e for e in ENDPOINTS if e[0] != "GET"]


def _call(client, method, path, body, headers):
    kwargs = {"headers": headers}
    if body is not None:
        kwargs["json"] = body
    return client.request(method, path, **kwargs)


@pytest.fixture
def api(engine, monkeypatch):
    """The app wired to the test database, with a known household.

    Not used as a context manager: that would run the lifespan handler, which
    migrates the real database rather than this one.
    """
    monkeypatch.setattr(config, "HOUSEHOLD", f"{OWNER_LOGIN},{OTHER_LOGIN}")

    def _session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _session_override
    yield TestClient(app)
    app.dependency_overrides.clear()


def _as(login: str) -> dict[str, str]:
    return {"Tailscale-User-Login": login, **CSRF}


# --------------------------------------------------------------------------- #
# Refusals
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("method,path,body", ENDPOINTS)
def test_no_identity_header_is_401(api, method, path, body):
    """Specifically not a 200 carrying user 1's data, which is what the old
    default would have produced."""
    response = _call(api, method, path, body, CSRF)
    assert response.status_code == 401


@pytest.mark.parametrize("method,path,body", ENDPOINTS)
def test_a_login_outside_the_household_is_403(api, method, path, body):
    response = _call(api, method, path, body, _as("stranger@example.com"))
    assert response.status_code == 403
    assert "stranger@example.com" in response.json()["detail"]


@pytest.mark.parametrize("method,path,body", UNSAFE_ENDPOINTS)
def test_an_unsafe_method_without_the_csrf_header_is_403(api, method, path, body):
    """Identity is ambient here, so a cross-site form submit arrives
    authenticated. A form cannot set a custom header; that is the whole defense."""
    response = _call(api, method, path, body, {"Tailscale-User-Login": OWNER_LOGIN})
    assert response.status_code == 403
    assert config.CSRF_HEADER in response.json()["detail"].lower()


def test_a_safe_method_needs_no_csrf_header(api):
    response = api.get("/api/feeds", headers={"Tailscale-User-Login": OWNER_LOGIN})
    assert response.status_code == 200


@pytest.mark.parametrize("variant", [OWNER_LOGIN.upper(), f"  {OWNER_LOGIN}  "])
def test_a_login_is_matched_case_and_whitespace_insensitively(api, variant):
    """One person who types their address differently is still one account."""
    response = api.get("/api/me", headers={"Tailscale-User-Login": variant})
    assert response.status_code == 200
    assert response.json()["login"] == OWNER_LOGIN


# --------------------------------------------------------------------------- #
# Isolation
# --------------------------------------------------------------------------- #
@pytest.fixture
def their_feed(session, client, feed_url, other_id):
    """A feed and its items belonging to the OTHER user."""
    return service.add_feed(session, feed_url, other_id, client=client)


def test_feeds_are_listed_per_person(api, their_feed):
    mine = api.get("/api/feeds", headers=_as(OWNER_LOGIN))
    theirs = api.get("/api/feeds", headers=_as(OTHER_LOGIN))
    assert mine.json() == []
    assert [f["id"] for f in theirs.json()] == [their_feed.id]


def test_items_are_listed_per_person(api, their_feed):
    mine = api.get("/api/items?days=0", headers=_as(OWNER_LOGIN))
    theirs = api.get("/api/items?days=0", headers=_as(OTHER_LOGIN))
    assert mine.json() == []
    assert len(theirs.json()) > 0


def test_unread_counts_are_per_person(api, their_feed):
    mine = api.get("/api/unread", headers=_as(OWNER_LOGIN)).json()
    theirs = api.get("/api/unread", headers=_as(OTHER_LOGIN)).json()
    assert mine["total"] == 0
    assert theirs["total"] > 0


def test_one_person_cannot_read_anothers_item(api, session, their_feed, other_id):
    item = service.list_items(session, other_id, days=None)[0]
    response = api.post(f"/api/items/{item.id}/read", json={"read": True}, headers=_as(OWNER_LOGIN))
    assert response.status_code == 404
    session.refresh(item)
    assert item.read is False


def test_one_person_cannot_delete_anothers_feed(api, session, their_feed, other_id):
    response = api.delete(f"/api/feeds/{their_feed.id}", headers=_as(OWNER_LOGIN))
    assert response.status_code == 404
    assert len(service.list_feeds(session, other_id)) == 1


def test_mark_all_read_stops_at_the_person_who_asked(api, session, their_feed, other_id):
    response = api.post("/api/items/read-all", headers=_as(OWNER_LOGIN))
    assert response.status_code == 200
    assert response.json()["updated"] == 0
    assert all(not i.read for i in service.list_items(session, other_id, days=None))


def test_refresh_only_touches_the_callers_feeds(api, their_feed):
    response = api.post("/api/refresh", headers=_as(OWNER_LOGIN))
    assert response.status_code == 200
    assert response.json() == []


def test_a_first_time_household_member_starts_empty(api, their_feed, session):
    """A new person gets their own account rather than a share of somebody's."""
    from sqlmodel import select

    from rss_reader.models import User

    before = len(session.exec(select(User)).all())
    response = api.get("/api/feeds", headers=_as(OWNER_LOGIN))
    assert response.status_code == 200
    assert response.json() == []
    assert len(session.exec(select(User)).all()) == before
