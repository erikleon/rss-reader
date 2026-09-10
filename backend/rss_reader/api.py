"""FastAPI application: JSON API under /api, plus the built frontend if present.

Every ``/api`` route depends on ``get_current_user``. There is no unauthenticated
route and no default user to fall back to, because a fallback would look exactly
like success while serving one person's feeds to everybody.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import Session

from . import auth, config, opml, scheduler, service
from .db import get_session, init_db
from .models import Feed, Item, User

# Path to the built Svelte frontend (frontend/dist), served when present.
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Parse the allowlist here so a missing or empty one stops the app, rather
    # than surfacing as a 403 for every person in turn.
    auth.household()
    scheduler.start(app)
    yield
    await scheduler.stop(app)


app = FastAPI(title="rss-reader", lifespan=lifespan)

# The Vite dev server is a different origin, so it needs CORS. In production
# nothing legitimate is cross-origin, and leaving this on would weaken the
# preflight that backs up the CSRF header check.
if os.environ.get("RSS_READER_DEV_CORS") == "1":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )


CurrentUser = Depends(auth.get_current_user)


# --------------------------------------------------------------------------- #
# Request/response schemas
# --------------------------------------------------------------------------- #
class AddFeedRequest(BaseModel):
    url: str


class ReadRequest(BaseModel):
    read: bool


class RefreshFeedResult(BaseModel):
    id: int
    title: str
    new_count: int
    error: str | None = None


# --------------------------------------------------------------------------- #
# Feeds
# --------------------------------------------------------------------------- #
@app.get("/api/feeds", response_model=list[Feed])
def get_feeds(
    user: User = CurrentUser, session: Session = Depends(get_session)
) -> list[Feed]:
    return service.list_feeds(session, user.id)


@app.post("/api/feeds", response_model=Feed, status_code=201)
def post_feed(
    body: AddFeedRequest,
    user: User = CurrentUser,
    session: Session = Depends(get_session),
) -> Feed:
    try:
        return service.add_feed(session, body.url, user.id)
    except service.FeedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/feeds/{feed_id}", status_code=204)
def delete_feed(
    feed_id: int, user: User = CurrentUser, session: Session = Depends(get_session)
) -> None:
    try:
        service.remove_feed(session, feed_id, user.id)
    except service.FeedError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# --------------------------------------------------------------------------- #
# Refresh & items
# --------------------------------------------------------------------------- #
@app.post("/api/refresh", response_model=list[RefreshFeedResult])
def post_refresh(
    user: User = CurrentUser, session: Session = Depends(get_session)
) -> list[RefreshFeedResult]:
    results = service.refresh_all(session, user.id)
    return [
        RefreshFeedResult(id=r.feed_id, title=r.title, new_count=r.new_count, error=r.error)
        for r in results
    ]


@app.get("/api/items", response_model=list[Item])
def get_items(
    days: int = config.DEFAULT_DAYS,
    unread_only: bool = False,
    before: datetime | None = None,
    q: str | None = None,
    user: User = CurrentUser,
    session: Session = Depends(get_session),
) -> list[Item]:
    # days <= 0 means "all history" (useful when searching).
    window = days if days > 0 else None
    return service.list_items(
        session, user.id, days=window, unread_only=unread_only, before=before, query=q
    )


@app.post("/api/items/{item_id}/read", response_model=Item)
def post_item_read(
    item_id: int,
    body: ReadRequest,
    user: User = CurrentUser,
    session: Session = Depends(get_session),
) -> Item:
    try:
        return service.set_read(session, item_id, body.read, user.id)
    except service.FeedError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/items/read-all")
def post_read_all(
    user: User = CurrentUser, session: Session = Depends(get_session)
) -> dict[str, int]:
    return {"updated": service.mark_all_read(session, user.id)}


@app.get("/api/unread")
def get_unread(
    user: User = CurrentUser, session: Session = Depends(get_session)
) -> dict[str, object]:
    counts = service.unread_counts(session, user.id)
    return {"total": sum(counts.values()), "by_feed": counts}


@app.get("/api/me")
def get_me(user: User = CurrentUser) -> dict[str, object]:
    """Who the server thinks you are.

    Under header identity the browser has no way to answer "why am I looking at
    somebody else's feeds", because it never sent a name. This is that answer.
    """
    return {"id": user.id, "login": user.username}


# --------------------------------------------------------------------------- #
# OPML import
# --------------------------------------------------------------------------- #
@app.post("/api/import/opml")
async def post_import_opml(
    request: Request,
    user: User = CurrentUser,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    """Import subscriptions from a raw OPML body (text/xml)."""
    body = await request.body()
    try:
        result = service.import_opml(session, body, user.id)
    except opml.OpmlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "added": len(result.added),
        "skipped": len(result.skipped),
        "failed": [{"url": u, "error": e} for u, e in result.failed],
    }


# --------------------------------------------------------------------------- #
# Static frontend (mounted last so it doesn't shadow /api routes)
# --------------------------------------------------------------------------- #
if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
