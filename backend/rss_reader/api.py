"""FastAPI application: JSON API under /api, plus the built frontend if present."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import Session

from . import config, service
from .db import get_engine, init_db
from .models import Feed, Item

# Path to the built Svelte/Arrow frontend (frontend/dist), served when present.
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

app = FastAPI(title="rss-reader")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


def get_session():
    with Session(get_engine()) as session:
        yield session


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
def get_feeds(session: Session = Depends(get_session)) -> list[Feed]:
    return service.list_feeds(session)


@app.post("/api/feeds", response_model=Feed, status_code=201)
def post_feed(body: AddFeedRequest, session: Session = Depends(get_session)) -> Feed:
    try:
        return service.add_feed(session, body.url)
    except service.FeedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/feeds/{feed_id}", status_code=204)
def delete_feed(feed_id: int, session: Session = Depends(get_session)) -> None:
    try:
        service.remove_feed(session, feed_id)
    except service.FeedError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# --------------------------------------------------------------------------- #
# Refresh & items
# --------------------------------------------------------------------------- #
@app.post("/api/refresh", response_model=list[RefreshFeedResult])
def post_refresh(session: Session = Depends(get_session)) -> list[RefreshFeedResult]:
    results = service.refresh_all(session)
    return [
        RefreshFeedResult(id=r.feed_id, title=r.title, new_count=r.new_count, error=r.error)
        for r in results
    ]


@app.get("/api/items", response_model=list[Item])
def get_items(
    days: int = config.DEFAULT_DAYS,
    unread_only: bool = False,
    before: datetime | None = None,
    session: Session = Depends(get_session),
) -> list[Item]:
    return service.list_items(
        session, days=days, unread_only=unread_only, before=before
    )


@app.post("/api/items/{item_id}/read", response_model=Item)
def post_item_read(
    item_id: int, body: ReadRequest, session: Session = Depends(get_session)
) -> Item:
    try:
        return service.set_read(session, item_id, body.read)
    except service.FeedError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/items/read-all")
def post_read_all(session: Session = Depends(get_session)) -> dict[str, int]:
    return {"updated": service.mark_all_read(session)}


# --------------------------------------------------------------------------- #
# Static frontend (mounted last so it doesn't shadow /api routes)
# --------------------------------------------------------------------------- #
if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
