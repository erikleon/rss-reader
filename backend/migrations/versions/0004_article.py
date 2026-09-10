"""cached readable article bodies

Revision ID: 0004_article
Revises: 0003_user_login
Create Date: 2026-09-10

One row per item, created the first time somebody opens the reader view for it.
ON DELETE CASCADE so deleting a feed or pruning old items takes the cached
bodies with them: these are the largest rows in the database and an orphaned one
is unreachable, so it would be pure growth.

The cascade is declared and foreign_keys=ON is set on every connection (see
db._apply_pragmas), which is what makes it actually fire. SQLite ignores foreign
keys entirely by default, so the declaration alone would be decoration.
"""
from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "0004_article"
down_revision = "0003_user_login"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "articles",
        sa.Column("item_id", sa.Integer(), primary_key=True),
        sa.Column("url", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("html", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("articles")
