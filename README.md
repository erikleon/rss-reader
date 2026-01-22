# rss-reader

A simple personal RSS reader. Subscribe to feeds, pull new items on demand, and read
them in a clean view **grouped by day** with read/unread tracking. Usable as a **web app**
(FastAPI + Svelte) or a **CLI** — both share the same core.

## Features

- Add / remove feed subscriptions (RSS and Atom), with **autodiscovery** — paste a site
  homepage and the real feed URL is found from its `<link rel="alternate">` tags
- Manual refresh plus **background auto-refresh** on a configurable interval
- **OPML import** (web UI, CLI, or API) to bring subscriptions over from another reader
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
cd frontend && npm run dev  # frontend dev server, proxies /api to :8000
```

### Docker

A multi-stage build compiles the frontend and serves it together with the API:

```bash
docker build -t rss-reader .
docker run -p 8000:8000 -v rss-reader-data:/data rss-reader
```

The database is persisted in the `/data` volume.

### CLI

```bash
rss-reader feed add https://hnrss.org/frontpage   # or paste a site homepage (autodiscovery)
rss-reader refresh
rss-reader items --days 30          # grouped by day; --unread for unread only
rss-reader read <item_id>           # or: unread <item_id> / read-all
rss-reader import subscriptions.opml
rss-reader prune --days 90          # delete read items older than 90 days (--all incl. unread)
rss-reader feed list
```

The SQLite database lives at `~/.rss-reader/rss_reader.db` (override with `RSS_READER_DB`).
The schema is managed by Alembic and applied automatically on startup; after changing a
model, generate a migration with `alembic revision --autogenerate -m "describe change"`.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `RSS_READER_DB` | `~/.rss-reader/rss_reader.db` | SQLite database location |
| `RSS_READER_AUTO_REFRESH` | `1` | Background auto-refresh (`0` to disable) |
| `RSS_READER_REFRESH_INTERVAL` | `900` | Auto-refresh interval, seconds |
| `RSS_READER_CONCURRENCY` | `8` | Max feeds fetched in parallel per refresh |
| `RSS_READER_RETENTION_DAYS` | `0` | Auto-prune read items older than N days (`0` = keep all) |
| `RSS_READER_TIMEOUT` | `15` | Per-feed fetch timeout, seconds |

## Testing

```bash
pytest          # backend, offline (uses a local feed fixture)
cd frontend && npm run check   # Svelte/TS type check
```
