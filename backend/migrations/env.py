"""Alembic environment, wired to the app's models and database URL."""

from __future__ import annotations

import sqlmodel
from alembic import context
from sqlalchemy import create_engine, pool

# Importing the models registers their tables on SQLModel.metadata so
# autogenerate can diff against them.
from rss_reader import config as app_config
from rss_reader import models  # noqa: F401  (import for side effect)

target_metadata = sqlmodel.SQLModel.metadata


def _url() -> str:
    return context.config.get_main_option("sqlalchemy.url") or app_config.database_url()


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
