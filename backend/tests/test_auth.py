"""Identity resolution: the allowlist, normalization, and account provisioning."""

from __future__ import annotations

import pytest
from sqlmodel import select

from rss_reader import auth, config
from rss_reader.models import User

from conftest import OTHER_LOGIN, OWNER_LOGIN


# --------------------------------------------------------------------------- #
# parse_household
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("a@x.com", ["a@x.com"]),
        ("a@x.com,b@x.com", ["a@x.com", "b@x.com"]),
        ("  a@x.com , b@x.com  ", ["a@x.com", "b@x.com"]),
        ("A@X.com,a@x.COM", ["a@x.com"]),  # one person, typed twice
        ("a@x.com,,b@x.com,", ["a@x.com", "b@x.com"]),
        ("a@x.com\n,\tb@x.com", ["a@x.com", "b@x.com"]),
    ],
)
def test_parse_household_accepts_the_forms_people_actually_type(raw, expected):
    assert auth.parse_household(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", ",", " , , "])
def test_parse_household_refuses_an_empty_allowlist(raw):
    """Starting with no allowlist means refusing everybody or admitting
    everybody, and both are worse than not starting."""
    with pytest.raises(auth.HouseholdError):
        auth.parse_household(raw)


@pytest.mark.parametrize(
    "raw,normalized",
    [("  Person@Example.com  ", "person@example.com"), ("PERSON@EXAMPLE.COM", "person@example.com")],
)
def test_normalize_login_collapses_case_and_whitespace(raw, normalized):
    assert auth.normalize_login(raw) == normalized


# --------------------------------------------------------------------------- #
# get_or_create_user
# --------------------------------------------------------------------------- #
def test_existing_login_resolves_to_its_own_row(session):
    user = auth.get_or_create_user(session, OTHER_LOGIN)
    assert user.username == OTHER_LOGIN
    assert user.id != config.DEFAULT_USER_ID


def test_a_new_login_gets_a_new_account(session):
    before = len(session.exec(select(User)).all())
    user = auth.get_or_create_user(session, "new@example.com")
    assert user.id not in (config.DEFAULT_USER_ID,)
    assert len(session.exec(select(User)).all()) == before + 1


def test_the_same_login_twice_is_one_account(session):
    first = auth.get_or_create_user(session, "new@example.com")
    second = auth.get_or_create_user(session, "new@example.com")
    assert first.id == second.id


def test_the_first_login_claims_the_pre_auth_account(session):
    """A database from before auth has one row holding all the feeds. The first
    identified person takes it over rather than starting empty beside it."""
    legacy = session.get(User, config.DEFAULT_USER_ID)
    legacy.username = config.LEGACY_USERNAME
    session.add(legacy)
    session.commit()

    user = auth.get_or_create_user(session, "first@example.com")

    assert user.id == config.DEFAULT_USER_ID
    assert user.username == "first@example.com"


def test_only_the_first_login_claims_it(session):
    """The second person gets their own account, not a share of the first's."""
    legacy = session.get(User, config.DEFAULT_USER_ID)
    legacy.username = config.LEGACY_USERNAME
    session.add(legacy)
    session.commit()

    first = auth.get_or_create_user(session, "first@example.com")
    second = auth.get_or_create_user(session, "second@example.com")

    assert first.id == config.DEFAULT_USER_ID
    assert second.id != first.id


def test_a_populated_account_is_never_claimed(session):
    """OWNER_LOGIN already owns user 1, so a different login must not land on
    it and inherit their feeds."""
    user = auth.get_or_create_user(session, "someone-else@example.com")
    assert user.id != config.DEFAULT_USER_ID
    assert session.get(User, config.DEFAULT_USER_ID).username == OWNER_LOGIN
