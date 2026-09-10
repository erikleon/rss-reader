"""users.username becomes the non-null Tailscale login

Revision ID: 0003_user_login
Revises: 0002_feed_conditional_get
Create Date: 2026-09-10

The pre-auth database holds one row, ``username="default"``, which is a
placeholder rather than anybody's login. It is left in place: the first
identified request claims it (see auth.get_or_create_user) so feeds added before
auth existed stay with the person who added them.

Rows with no username at all cannot be claimed and cannot be reached, so they
get a synthetic one rather than being deleted. Dropping them would take their
feeds with them.

SQLite cannot ALTER a column, so this rebuilds the table. ``copy_from`` supplies
the schema explicitly because the unique constraint from 0001 is unnamed, and
reflecting an unnamed constraint into a batch operation is exactly where this
kind of migration goes wrong.
"""
from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "0003_user_login"
down_revision = "0002_feed_conditional_get"
branch_labels = None
depends_on = None


def _users_table(nullable: bool) -> sa.Table:
    return sa.Table(
        "users",
        sa.MetaData(),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sqlmodel.sql.sqltypes.AutoString(), nullable=nullable),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )


def _fill_missing_usernames() -> None:
    users = sa.table("users", sa.column("id", sa.Integer), sa.column("username", sa.String))
    op.execute(
        users.update()
        .where(users.c.username.is_(None))
        .values(username=sa.literal_column("'user-' || id"))
    )


def upgrade() -> None:
    _fill_missing_usernames()
    with op.batch_alter_table("users", copy_from=_users_table(nullable=True)) as batch:
        batch.alter_column(
            "username",
            existing_type=sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("users", copy_from=_users_table(nullable=False)) as batch:
        batch.alter_column(
            "username",
            existing_type=sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        )
