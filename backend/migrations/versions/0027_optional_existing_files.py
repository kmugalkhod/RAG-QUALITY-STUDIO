"""Persist optional Existing Files selections and terminal excluded items.

Revision ID: 0027
Revises: 0026
"""

import sqlalchemy as sa
from alembic import op


revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ingestion_run_items",
        sa.Column(
            "is_optional", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.drop_constraint("ck_ingestion_item_status", "ingestion_run_items", type_="check")
    op.create_check_constraint(
        "ck_ingestion_item_status",
        "ingestion_run_items",
        "status IN ('processing','ready','succeeded','excluded','failed','cancelled')",
    )
    op.drop_constraint("ck_ingestion_run_complete", "ingestion_runs", type_="check")
    op.create_check_constraint(
        "ck_ingestion_run_complete",
        "ingestion_runs",
        "status != 'succeeded' OR "
        "(stage = 'complete' AND progress = 100 AND published_count = 1 "
        "AND processed_count + failed_count = discovered_count "
        "AND embedded_count = chunk_count)",
    )


def downgrade():
    partial = op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM ingestion_runs "
            "WHERE status = 'succeeded' AND failed_count > 0"
        )
    )
    if partial:
        raise RuntimeError(
            "Cannot downgrade while successful runs contain excluded items."
        )
    op.drop_constraint("ck_ingestion_run_complete", "ingestion_runs", type_="check")
    op.create_check_constraint(
        "ck_ingestion_run_complete",
        "ingestion_runs",
        "status != 'succeeded' OR "
        "(stage = 'complete' AND progress = 100 AND published_count = 1 "
        "AND processed_count = discovered_count AND failed_count = 0 "
        "AND embedded_count = chunk_count)",
    )
    op.execute(
        "UPDATE ingestion_run_items SET status = 'failed' WHERE status = 'excluded'"
    )
    op.drop_constraint("ck_ingestion_item_status", "ingestion_run_items", type_="check")
    op.create_check_constraint(
        "ck_ingestion_item_status",
        "ingestion_run_items",
        "status IN ('processing','ready','succeeded','failed','cancelled')",
    )
    op.drop_column("ingestion_run_items", "is_optional")
