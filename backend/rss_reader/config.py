"""Runtime configuration, overridable via environment variables."""

from __future__ import annotations

import os
from pathlib import Path

# The single default user used while the app is single-user. Multi-user support
# later just means resolving a different id from an authenticated request.
DEFAULT_USER_ID = 1

# Default number of days of history shown in a single view.
DEFAULT_DAYS = 30

# Network fetch settings.
FETCH_TIMEOUT = float(os.environ.get("RSS_READER_TIMEOUT", "15"))
USER_AGENT = "rss-reader/0.1 (+https://github.com/local/rss-reader)"

# Length (characters) a summary snippet is truncated to.
SNIPPET_LENGTH = 280

# Background auto-refresh. Disable with RSS_READER_AUTO_REFRESH=0; tune the
# interval (seconds) with RSS_READER_REFRESH_INTERVAL.
AUTO_REFRESH = os.environ.get("RSS_READER_AUTO_REFRESH", "1") not in ("0", "false", "False", "")
REFRESH_INTERVAL = int(os.environ.get("RSS_READER_REFRESH_INTERVAL", "900"))


def db_path() -> Path:
    """Location of the SQLite file. Override with RSS_READER_DB."""
    override = os.environ.get("RSS_READER_DB")
    if override:
        return Path(override)
    return Path.home() / ".rss-reader" / "rss_reader.db"


def database_url() -> str:
    """SQLAlchemy URL for the SQLite database, ensuring the parent dir exists."""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"
