"""add etag/last_modified to feeds

Revision ID: 0002_feed_conditional_get
Revises: 0001_baseline
Create Date: 2026-01-16
"""
from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "0002_feed_conditional_get"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "feeds",
        sa.Column("etag", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.add_column(
        "feeds",
        sa.Column("last_modified", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("feeds", "last_modified")
    op.drop_column("feeds", "etag")
