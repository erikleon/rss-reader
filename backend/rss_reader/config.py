"""Runtime configuration, overridable via environment variables."""

from __future__ import annotations

import os
from pathlib import Path

# The row that held everything while the app was single-user. It is not a
# fallback identity: nothing resolves to it unless a real login claims it (see
# auth.get_or_create_user). Kept so a pre-auth database keeps its feeds.
DEFAULT_USER_ID = 1
LEGACY_USERNAME = "default"

# Default number of days of history shown in a single view.
DEFAULT_DAYS = 30

# Address the web app binds. Loopback by default: identity arrives in a header
# and that is only trustworthy while the ingress is the sole route in.
HOST = os.environ.get("RSS_READER_HOST", "127.0.0.1")

# Comma-separated Tailscale logins allowed to use this reader. No default; an
# empty value is refused at startup rather than guessed at.
HOUSEHOLD = os.environ.get("RSS_READER_HOUSEHOLD")

# Login the CLI acts as when --user is not given.
CLI_USER = os.environ.get("RSS_READER_CLI_USER")

# Header the frontend sends on state-changing requests. Its value is irrelevant;
# what matters is that a cross-site form cannot set it at all.
CSRF_HEADER = "x-rss-reader"

# Network fetch settings.
FETCH_TIMEOUT = float(os.environ.get("RSS_READER_TIMEOUT", "15"))
USER_AGENT = "rss-reader/0.1 (+https://github.com/local/rss-reader)"

# Refuse fetches that resolve to loopback, private, link-local or reserved
# addresses. Subscribing to a feed makes the server fetch a URL somebody else
# chose, so without this every household member can reach services that only
# listen on internal addresses. Off only for the offline tests, which fetch
# hostnames that deliberately do not resolve.
FETCH_GUARD = os.environ.get("RSS_READER_FETCH_GUARD", "1") not in ("0", "false", "False")

# Redirects are followed by hand so every hop is checked, not just the first.
FETCH_MAX_REDIRECTS = int(os.environ.get("RSS_READER_MAX_REDIRECTS", "5"))

# Ceiling on a single fetched body. A feed is text; anything this large is a
# mistake or a deliberate one.
FETCH_MAX_BYTES = int(os.environ.get("RSS_READER_MAX_BYTES", str(5 * 1024 * 1024)))

# Length (characters) a summary snippet is truncated to.
SNIPPET_LENGTH = 280

# Background auto-refresh. Disable with RSS_READER_AUTO_REFRESH=0; tune the
# interval (seconds) with RSS_READER_REFRESH_INTERVAL.
AUTO_REFRESH = os.environ.get("RSS_READER_AUTO_REFRESH", "1") not in ("0", "false", "False", "")
REFRESH_INTERVAL = int(os.environ.get("RSS_READER_REFRESH_INTERVAL", "900"))

# Max feeds fetched in parallel during a refresh.
REFRESH_CONCURRENCY = int(os.environ.get("RSS_READER_CONCURRENCY", "8"))

# Auto-prune read items older than this many days after each auto-refresh.
# 0 disables retention (keep everything).
RETENTION_DAYS = int(os.environ.get("RSS_READER_RETENTION_DAYS", "0"))

# How long a connection waits for a SQLite lock before giving up, in seconds.
# The background refresh commits while browsers are reading; without this a
# collision surfaces as a 500 rather than a short wait.
SQLITE_BUSY_TIMEOUT = float(os.environ.get("RSS_READER_BUSY_TIMEOUT", "10"))


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
