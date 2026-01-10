# rss-reader

A simple personal RSS reader. Subscribe to feeds, pull new items on demand, and read
them in a clean view **grouped by day** with read/unread tracking. Usable as a **web app**
(FastAPI + Svelte) or a **CLI** — both share the same core.

## Features

- Add / remove feed subscriptions (RSS and Atom)
- Manual refresh that dedupes items and isolates per-feed errors
- Items grouped by day, newest first; title + source + time + snippet, link opens the original
- Read/unread tracking, with an "unread only" filter and "mark all read"
- Single-user today, but the data model and service layer are scoped by `user_id` so auth /
  multi-user can be added later without a schema rewrite

## Architecture

A shared core (`backend/rss_reader`) holds storage, fetching, and the service functions used by
both surfaces:

- `models.py` — SQLModel tables (`User`, `Feed`, `Item`) over SQLite
- `fetcher.py` — httpx fetch + feedparser normalization (no DB concerns; unit-tested offline)
- `service.py` — core ops (`add_feed`, `refresh_all`, `list_items`, `set_read`, `group_by_day`, …)
- `api.py` — FastAPI JSON API under `/api` (also serves the built frontend)
- `cli.py` — Typer CLI

The frontend (`frontend/`) is Svelte + TypeScript built with Vite.

## Setup

Backend (Python 3.11+):

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows;  source .venv/bin/activate on macOS/Linux
pip install -e ".[dev]"
```

Frontend (Node 18+):

```bash
cd frontend
npm install
```

## Running

### Web app (single process)

Build the frontend once, then serve everything from FastAPI:

```bash
cd frontend && npm run build && cd ..
rss-reader serve            # http://127.0.0.1:8000
```

### Web app (dev, with hot reload)

```bash
rss-reader serve --reload   # backend on :8000
cd frontend && npm run dev  # frontend on :5173, proxies /api to :8000
```

### CLI

```bash
rss-reader feed add https://hnrss.org/frontpage
rss-reader refresh
rss-reader items --days 30          # grouped by day; --unread for unread only
rss-reader read <item_id>           # or: unread <item_id> / read-all
rss-reader feed list
```

The SQLite database lives at `~/.rss-reader/rss_reader.db` (override with `RSS_READER_DB`).

## Testing

```bash
pytest          # backend, offline (uses a local feed fixture)
cd frontend && npm run check   # Svelte/TS type check
```
