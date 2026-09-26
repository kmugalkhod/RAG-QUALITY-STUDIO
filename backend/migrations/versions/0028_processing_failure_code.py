"""Persist safe processing failure codes for ingestion decisions.

Revision ID: 0028
Revises: 0027
"""

import sqlalchemy as sa
from alembic import op


revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("processing_runs", sa.Column("error_code", sa.String(80)))


def downgrade():
    op.drop_column("processing_runs", "error_code")
