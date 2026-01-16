"""baseline schema

Revision ID: 0001_baseline
Revises:
Create Date: 2026-01-15
"""
from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "feeds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("url", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("site_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.Column("last_fetched_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("user_id", "url", name="uq_feed_user_url"),
    )
    op.create_index("ix_feeds_user_id", "feeds", ["user_id"])
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("feed_id", sa.Integer(), nullable=False),
        sa.Column("guid", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("link", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("summary", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("read", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["feed_id"], ["feeds.id"]),
        sa.UniqueConstraint("feed_id", "guid", name="uq_item_feed_guid"),
    )
    op.create_index("ix_items_feed_id", "items", ["feed_id"])
    op.create_index("ix_items_published_at", "items", ["published_at"])
    op.create_index("ix_items_read", "items", ["read"])


def downgrade() -> None:
    op.drop_table("items")
    op.drop_table("feeds")
    op.drop_table("users")
