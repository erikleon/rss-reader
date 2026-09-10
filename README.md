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
- **Reader view**: open an article inside the reader, stripped to the text, with
  no navigation, no sidebars and no scripts
- **Multi-user, with identity from the ingress.** Each person gets their own
  subscriptions and their own read state. There are no passwords: the app trusts
  the `Tailscale-User-Login` header that `tailscale serve` injects, checked
  against an allowlist

## Architecture

A shared core (`backend/rss_reader`) holds storage, fetching, and the service functions used by
both surfaces:

- `models.py` — SQLModel tables (`User`, `Feed`, `Item`) over SQLite
- `fetcher.py` — httpx fetch + feedparser normalization (no DB concerns; unit-tested offline)
- `service.py` — core ops (`add_feed`, `refresh_all`, `list_items`, `set_read`, `group_by_day`, …)
- `auth.py` — resolves a request's Tailscale login to a `User`
- `extract.py` — finds the article on a fetched page and sanitises it
- `api.py` — FastAPI JSON API under `/api` (also serves the built frontend)
- `cli.py` — Typer CLI

Every service function takes `user_id` and none of them default it. That is
deliberate: with several people in one database, a defaulted argument turns a
forgotten one into a silent read of somebody else's feeds instead of an error.

## Reader view

"Read here" on an item, or `r`, fetches the linked page and renders the article
without the furniture. The result is cached per item, so only the first open is
slow. Failures are cached too, because a page that cannot be read is a property
of the page; "Re-fetch" is the way past that.

Two separate things happen in `extract.py`, and the distinction matters:

**Extraction** picks which part of the page is the article, by scoring where
paragraphs cluster and then reassembling a body that is split across containers.
It is a heuristic and it is allowed to be wrong. The original is one click away.

**Sanitisation** decides what may reach the browser. It is an allowlist of tags
and attributes, never a list of things to strip, so a tag nobody thought of is
dropped rather than passed. Scripts, styles, iframes, forms and event handlers
do not survive; relative links and images are resolved against the page they
came from; every link opens away from the reader.

Fetching an article uses the same guarded path as fetching a feed, so an
article link pointing at loopback or a private address is refused. That guard
matters more here than anywhere else in the app: a feed URL is one a person
typed, and an article URL is one a stranger's feed chose.

## Identity

The app does not authenticate anybody. It reads `Tailscale-User-Login`, which
`tailscale serve` injects from the calling node's account, and checks it against
`RSS_READER_HOUSEHOLD`. A missing header is a 401, a login off the list is a 403,
and a login on it gets an account the first time it appears.

That header is worth exactly as much as the reachability of the port it arrives
on. `RSS_READER_HOST` defaults to loopback for this reason: anything that can
reach the app directly can claim to be anybody. Widen the bind only when
something else closes the door, such as a container port published on 127.0.0.1.

State-changing requests must also carry an `X-RSS-Reader` header. Identity here
is ambient, so without it a page on another site could make your browser mark
your feed read; a cross-site form cannot set a custom header.

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
docker run -p 127.0.0.1:8000:8000 \
  -e RSS_READER_HOST=0.0.0.0 \
  -e RSS_READER_HOUSEHOLD=you@example.com \
  -v rss-reader-data:/data rss-reader
```

The database is persisted in the `/data` volume.

`RSS_READER_HOST=0.0.0.0` binds every interface *inside the container's own
namespace*, which is what a published port connects to. The boundary is the
`127.0.0.1:` on the publish, not the bind: drop it and the reader answers on
your LAN as whoever asks. The image defaults to loopback so that forgetting this
produces a container nothing can reach, rather than one anybody can.

### CLI

Per-person commands take `--user <login>`, the same string the web app resolves,
falling back to `RSS_READER_CLI_USER`. `refresh` and `prune` are maintenance and
cover every user, so they take no `--user`.

```bash
rss-reader user list                # the valid --user values
rss-reader feed add https://hnrss.org/frontpage --user you@example.com
rss-reader items --days 30 --user you@example.com   # --unread for unread only
rss-reader read <item_id> --user you@example.com    # or: unread / read-all
rss-reader import subscriptions.opml --user you@example.com
rss-reader refresh                  # every user
rss-reader prune --days 90          # every user; --all includes unread
```

This is data selection, not authentication. Anyone who can run the CLI already
has the database.

The SQLite database lives at `~/.rss-reader/rss_reader.db` (override with `RSS_READER_DB`).
The schema is managed by Alembic and applied automatically on startup; after changing a
model, generate a migration with `alembic revision --autogenerate -m "describe change"`.

## Configuration

Copy `.env.example` to `.env` and adjust as needed; all variables are optional.

| Variable | Default | Purpose |
| --- | --- | --- |
| `RSS_READER_DB` | `~/.rss-reader/rss_reader.db` | SQLite database location |
| `RSS_READER_PORT` | `8000` | Port the web app (`rss-reader serve`) listens on |
| `RSS_READER_HOST` | `127.0.0.1` | Address to bind. See Identity above before widening it |
| `RSS_READER_HOUSEHOLD` | *(none)* | Comma-separated logins allowed in. Empty stops the app |
| `RSS_READER_CLI_USER` | *(none)* | Login the CLI acts as without `--user` |
| `RSS_READER_FETCH_GUARD` | `1` | Refuse fetches resolving to internal addresses |
| `RSS_READER_MAX_REDIRECTS` | `5` | Redirect hops followed, each one re-checked |
| `RSS_READER_MAX_BYTES` | `5242880` | Ceiling on one fetched body |
| `RSS_READER_BUSY_TIMEOUT` | `10` | Seconds to wait on a SQLite lock |
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
