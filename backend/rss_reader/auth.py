"""Identity: resolve a request's Tailscale login to a ``User`` row.

The app is fronted by ``tailscale serve``, which injects the account the calling
node is signed in with as ``Tailscale-User-Login``. That header is trustworthy
only because nothing else can reach the port: the container publishes on
127.0.0.1 and serve is the sole route in. If the bind ever widens, this whole
module is decoration, which is why ``config.HOST`` defaults to loopback.

Two refusals, and they mean different things. A missing header is 401: the
request did not come through the ingress. A login that is not in
``RSS_READER_HOUSEHOLD`` is 403: the ingress vouched for somebody who is not a
member here.
"""

from __future__ import annotations

import logging

from fastapi import Depends, Header, HTTPException, Request
from sqlmodel import Session, select

from . import config
from .db import get_session
from .models import User

log = logging.getLogger("rss_reader.auth")

# Methods that cannot change state, so they need no CSRF header.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class HouseholdError(Exception):
    """Raised at startup when the household allowlist is unusable."""


def normalize_login(login: str) -> str:
    """Canonical form of an identity string.

    Logins arrive from an external system and people retype them into config, so
    case and surrounding whitespace must not create a second account for one
    person.
    """
    return login.strip().lower()


def parse_household(raw: str | None) -> list[str]:
    """Parse ``RSS_READER_HOUSEHOLD`` into an ordered, de-duplicated list.

    Raises ``HouseholdError`` when the result is empty. Starting with an empty
    allowlist would mean either refusing everybody or admitting everybody, and
    both are worse than refusing to start.
    """
    logins: list[str] = []
    for part in (raw or "").split(","):
        login = normalize_login(part)
        if login and login not in logins:
            logins.append(login)
    if not logins:
        raise HouseholdError(
            "RSS_READER_HOUSEHOLD is empty. Set it to a comma-separated list of "
            "the Tailscale logins allowed to use this reader."
        )
    return logins


def household() -> list[str]:
    """The parsed allowlist. Call at startup so a bad value fails loudly."""
    return parse_household(config.HOUSEHOLD)


def get_or_create_user(session: Session, login: str) -> User:
    """Resolve a normalized login to a ``User``, creating one on first sight.

    The operator's login is mapped onto the pre-existing user id 1 rather than
    getting a second account, so feeds added before this change stay theirs.
    """
    user = session.exec(select(User).where(User.username == login)).first()
    if user is not None:
        return user

    legacy = session.get(User, config.DEFAULT_USER_ID)
    if legacy is not None and legacy.username == config.LEGACY_USERNAME:
        # First identified request claims the single-user account.
        legacy.username = login
        session.add(legacy)
        session.commit()
        session.refresh(legacy)
        log.info("claimed the pre-auth account for login=%r", login)
        return legacy

    user = User(username=login)
    session.add(user)
    session.commit()
    session.refresh(user)
    log.info("provisioned user id=%s login=%r", user.id, login)
    return user


def require_csrf_header(request: Request) -> None:
    """Reject unsafe methods that do not carry the client's own header.

    Identity here is ambient: serve injects it from the connection, so a request
    a different site told the browser to make is authenticated too. A cross-site
    form cannot set a custom header, and a cross-site ``fetch`` that tries one
    triggers a preflight this app does not answer.
    """
    if request.method in _SAFE_METHODS:
        return
    if request.headers.get(config.CSRF_HEADER) is None:
        raise HTTPException(
            status_code=403,
            detail=f"{config.CSRF_HEADER} header required on {request.method} requests.",
        )


def get_current_user(
    tailscale_user_login: str | None = Header(default=None),
    session: Session = Depends(get_session),
    _csrf: None = Depends(require_csrf_header),
) -> User:
    """FastAPI dependency: the person this request belongs to.

    Fails closed. There is no fallback to a default user, because a fallback is
    indistinguishable from success and would serve one person's feeds to
    everybody.
    """
    if not tailscale_user_login:
        raise HTTPException(
            status_code=401,
            detail="No Tailscale identity on this request. Reach this app through "
            "its tailnet address rather than directly.",
        )

    login = normalize_login(tailscale_user_login)
    if login not in household():
        log.warning("refused login=%r: not in the household allowlist", login)
        raise HTTPException(
            status_code=403,
            detail=f"{login} is not a member of this household.",
        )
    return get_or_create_user(session, login)
