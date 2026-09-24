"""Persist reproducible duplicate decisions and language metadata.

Revision ID: 0024
Revises: 0023
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "content_derivations",
        sa.Column(
            "language",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    for table in (
        "ingestion_run_items",
        "website_run_items",
        "source_preview_items",
    ):
        op.add_column(
            table,
            sa.Column(
                "duplicate_decision",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
        )


def downgrade():
    for table in (
        "source_preview_items",
        "website_run_items",
        "ingestion_run_items",
    ):
        op.drop_column(table, "duplicate_decision")
    op.drop_column("content_derivations", "language")
