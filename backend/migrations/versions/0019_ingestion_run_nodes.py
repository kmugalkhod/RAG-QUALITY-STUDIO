"""Persist per-node ingestion execution checkpoints.

Revision ID: 0019
Revises: 0018
"""

import sqlalchemy as sa
from alembic import op


revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ingestion_run_nodes",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.String(length=120), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("node_type", sa.String(length=24), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="queued"
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "node_type IN ('source','extract','clean','chunk','embed','publish_index')",
            name="ck_ingestion_run_node_type",
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_ingestion_run_node_status",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "project_id"],
            ["ingestion_runs.id", "ingestion_runs.project_id"],
            name="fk_ingestion_run_node_run_project",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("run_id", "node_id"),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_ingestion_run_node_ordinal"),
    )
    op.create_index(
        "ix_ingestion_run_nodes_run_ordinal",
        "ingestion_run_nodes",
        ["run_id", "ordinal"],
    )


def downgrade():
    op.drop_index(
        "ix_ingestion_run_nodes_run_ordinal", table_name="ingestion_run_nodes"
    )
    op.drop_table("ingestion_run_nodes")
