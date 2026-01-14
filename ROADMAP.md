# Roadmap

Potential improvements, roughly prioritized by impact-to-effort. Nothing here is
committed scope — it's a backlog of ideas.

## Shipped

- ~~**Feed autodiscovery.**~~ Pasting a site homepage now resolves the real feed URL
  from its `<link rel="alternate">` tags.
- ~~**OPML import.**~~ Import subscriptions from an OPML file via the web UI
  ("Import OPML"), the `rss-reader import` CLI command, or `POST /api/import/opml`.

## High-value, low-effort

- **Background auto-refresh.** Periodically call `refresh_all` (asyncio task or
  APScheduler) on a configurable interval instead of only on manual click. Per-feed
  error isolation already exists, so this is mostly wiring.
- **OPML export.** Generate an OPML document from `list_feeds` (import already shipped).
- **Favicon / source icons.** Resolve each feed's site favicon at `add_feed` time and
  show it beside the source in `ItemRow`.
- **Feed-level filtering in the UI.** Click a feed in the sidebar to filter items to it
  (the API can already take a `feed_id`).

## Robustness / correctness

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
