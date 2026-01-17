"""Background auto-refresh: periodically pull all feeds while the server runs.

The refresh itself is synchronous (SQLModel sessions), so each cycle runs in a
worker thread to avoid blocking the event loop. A cycle never raises into the
loop, so one bad run can't kill the scheduler.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from . import config, service
from .db import session_scope

log = logging.getLogger("rss_reader.scheduler")


def run_refresh_cycle(engine=None, *, client: httpx.Client | None = None) -> int:
    """Run one refresh of every feed for every user. Returns total new items.

    When retention is configured, old items are pruned after refreshing.
    """
    with session_scope(engine) as session:
        results = service.refresh_all_users(session, client=client)
        if config.RETENTION_DAYS > 0:
            pruned = service.prune_all_users(session, days=config.RETENTION_DAYS)
            if pruned:
                log.info("retention: pruned %d old item(s)", pruned)
    return sum(r.new_count for feed_results in results.values() for r in feed_results)


async def _loop() -> None:
    while True:
        await asyncio.sleep(config.REFRESH_INTERVAL)
        try:
            total = await asyncio.to_thread(run_refresh_cycle)
            log.info("auto-refresh: %d new item(s)", total)
        except Exception:  # noqa: BLE001 - keep the scheduler alive across failures
            log.exception("auto-refresh cycle failed")


def start(app) -> None:
    """Start the background refresh task unless disabled in config."""
    if not config.AUTO_REFRESH or config.REFRESH_INTERVAL <= 0:
        log.info("auto-refresh disabled")
        return
    app.state.refresh_task = asyncio.create_task(_loop())
    log.info("auto-refresh every %ds", config.REFRESH_INTERVAL)


async def stop(app) -> None:
    """Cancel the background refresh task on shutdown."""
    task = getattr(app.state, "refresh_task", None)
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
