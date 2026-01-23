# Roadmap

Potential improvements, roughly prioritized by impact-to-effort. Nothing here is
committed scope — it's a backlog of ideas.

## Shipped

- ~~**Feed autodiscovery.**~~ Pasting a site homepage now resolves the real feed URL
  from its `<link rel="alternate">` tags.
- ~~**OPML import.**~~ Import subscriptions from an OPML file via the web UI
  ("Import OPML"), the `rss-reader import` CLI command, or `POST /api/import/opml`.
- ~~**Background auto-refresh.**~~ The server refreshes all feeds on a configurable
  interval (`RSS_READER_REFRESH_INTERVAL`, default 15m; disable with
  `RSS_READER_AUTO_REFRESH=0`); the web UI polls so new items surface automatically.
- ~~**Parallel refresh.**~~ Feeds are fetched concurrently (thread pool, capped by
  `RSS_READER_CONCURRENCY`) with DB writes kept serial.
- ~~**Migrations.**~~ Schema is managed by Alembic; `init_db` applies migrations on
  startup (and stamps pre-Alembic databases).
- ~~**Conditional GET.**~~ Per-feed ETag/Last-Modified are stored and sent as
  `If-None-Match`/`If-Modified-Since`; a 304 skips re-parsing.
- ~~**Retention / cleanup.**~~ `rss-reader prune` (and an opt-in auto-prune via
  `RSS_READER_RETENTION_DAYS`) drops old read items; `--all` includes unread.
- ~~**Frontend tests.**~~ Vitest unit tests for the pure functions (`parseUtc`,
  `groupByDay`), with a pinned timezone for determinism.
- ~~**Structured logging.**~~ Refresh runs log per-feed new/error lines and a run
  summary (`refresh complete user=… feeds=… new=… errors=…`).
- ~~**CI.**~~ GitHub Actions runs backend `pytest` and frontend
  check/test/build on every push and PR.
- ~~**Dockerfile.**~~ Multi-stage build (Node build → Python runtime) serving the API
  plus the built frontend from a single image; DB persisted on a `/data` volume.
- ~~**Relative timestamps.**~~ Items show "3h ago" style times (absolute time on hover).
- ~~**Unread counts.**~~ Per-feed unread badges in the sidebar and a total in the page title.

## High-value, low-effort

- **OPML export.** Generate an OPML document from `list_feeds` (import already shipped).
- **Favicon / source icons.** Resolve each feed's site favicon at `add_feed` time and
  show it beside the source in `ItemRow`.
- **Feed-level filtering in the UI.** Click a feed in the sidebar to filter items to it
  (the API can already take a `feed_id`).

## Multi-user path

- **Auth.** The model is already `user_id`-scoped. Add `password_hash` to `User`,
  session/JWT auth, and a `get_current_user` dependency replacing the hardcoded
  `DEFAULT_USER_ID` in `api.py`.
- **Normalize shared feeds.** Global `feeds` + per-user `subscriptions` + per-user read
  state, so many users on the same feed fetch once. Larger refactor; only worth it at scale.

## UX polish

- **Keyboard navigation** (`j`/`k` move, `o` open, `m` toggle read).
- **Mark-read-on-scroll** as an option.
- **Search** across stored titles/summaries via SQLite FTS5.
