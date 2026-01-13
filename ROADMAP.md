# Roadmap

Potential improvements, roughly prioritized by impact-to-effort. Nothing here is
committed scope — it's a backlog of ideas.

## High-value, low-effort

- **Background auto-refresh.** Periodically call `refresh_all` (asyncio task or
  APScheduler) on a configurable interval instead of only on manual click. Per-feed
  error isolation already exists, so this is mostly wiring.
- **OPML import / export.** Import loops `add_feed` over parsed OPML; export reads
  `list_feeds`. The standard way users migrate in and out of readers.
- **Favicon / source icons.** Resolve each feed's site favicon at `add_feed` time and
  show it beside the source in `ItemRow`.
- **Feed-level filtering in the UI.** Click a feed in the sidebar to filter items to it
  (the API can already take a `feed_id`).

## Robustness / correctness

- **Feed autodiscovery.** If a user pastes a site homepage, parse
  `<link rel="alternate" type="application/rss+xml">` and resolve the real feed URL.
- **Concurrent refresh.** Move `fetch_feed` to async `httpx.AsyncClient` and gather so
  many feeds refresh in parallel.
- **Conditional GET (ETag / Last-Modified).** Store per feed and send
  `If-None-Match` / `If-Modified-Since` to skip unchanged feeds (304).
- **Retention / cleanup.** A `prune` command/job to drop read items older than N days,
  since "keep everything" grows unbounded.
- **Migrations.** Adopt Alembic while the schema is small;
  `SQLModel.metadata.create_all` won't alter existing tables.

## Multi-user path

- **Auth.** The model is already `user_id`-scoped. Add `password_hash` to `User`,
  session/JWT auth, and a `get_current_user` dependency replacing the hardcoded
  `DEFAULT_USER_ID` in `api.py`.
- **Normalize shared feeds.** Global `feeds` + per-user `subscriptions` + per-user read
  state, so many users on the same feed fetch once. Larger refactor; only worth it at scale.

## UX polish

- **Keyboard navigation** (`j`/`k` move, `o` open, `m` toggle read).
- **Unread counts** per feed in the sidebar and a total in the page title.
- **Relative timestamps** ("3h ago") alongside the day grouping.
- **Mark-read-on-scroll** as an option.
- **Search** across stored titles/summaries via SQLite FTS5.

## Quality / ops

- **Frontend tests.** Unit-test the pure functions (`groupByDay`, `parseUtc`) with Vitest.
- **CI.** GitHub Actions running `pytest` + `npm run check` + `npm run build` on push.
- **Dockerfile.** Multi-stage build (npm build → copy `dist` → Python image) for the
  single-process `serve` deployment.
- **Structured logging** for refresh runs (feeds fetched, new counts, errors).
