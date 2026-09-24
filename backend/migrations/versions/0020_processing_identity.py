"""Persist exact processing identity and output hashes.

Revision ID: 0020
Revises: 0019
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "processing_runs",
        sa.Column("processing_config", postgresql.JSONB(astext_type=sa.Text())),
    )
    op.add_column(
        "processing_runs", sa.Column("processing_config_hash", sa.String(length=64))
    )
    op.add_column("processing_runs", sa.Column("output_hash", sa.String(length=64)))
    op.create_check_constraint(
        "ck_processing_run_config_hash",
        "processing_runs",
        "processing_config_hash IS NULL OR length(processing_config_hash) = 64",
    )
    op.create_check_constraint(
        "ck_processing_run_output_hash",
        "processing_runs",
        "output_hash IS NULL OR length(output_hash) = 64",
    )


def downgrade():
    op.drop_constraint(
        "ck_processing_run_output_hash", "processing_runs", type_="check"
    )
    op.drop_constraint(
        "ck_processing_run_config_hash", "processing_runs", type_="check"
    )
    op.drop_column("processing_runs", "output_hash")
    op.drop_column("processing_runs", "processing_config_hash")
    op.drop_column("processing_runs", "processing_config")
