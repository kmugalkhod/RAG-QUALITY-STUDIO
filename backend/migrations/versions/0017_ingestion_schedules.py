"""Add durable ingestion schedules.

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ingestion_schedules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_version_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="paused"),
        sa.Column("cadence", postgresql.JSONB(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_run_id", sa.Uuid()),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True)),
        sa.Column("last_outcome", sa.String(16)),
        sa.Column("last_error", sa.Text()),
        sa.Column("claim_token", sa.Uuid()),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["pipeline_version_id", "project_id"],
            ["pipeline_versions.id", "pipeline_versions.project_id"],
            name="fk_ingestion_schedule_version_project",
        ),
        sa.UniqueConstraint("id", "project_id", name="uq_ingestion_schedule_project"),
        sa.UniqueConstraint("project_id", "name", name="uq_ingestion_schedule_name"),
        sa.CheckConstraint(
            "status IN ('paused','enabled')", name="ck_ingestion_schedule_status"
        ),
        sa.CheckConstraint(
            "claim_token IS NULL OR claimed_at IS NOT NULL",
            name="ck_ingestion_schedule_claim",
        ),
    )
    op.create_index(
        "ix_ingestion_schedule_project_created",
        "ingestion_schedules",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_ingestion_schedule_due",
        "ingestion_schedules",
        ["next_run_at"],
        postgresql_where=sa.text("status = 'enabled'"),
    )
    op.add_column("ingestion_runs", sa.Column("schedule_id", sa.Uuid()))
    op.add_column(
        "ingestion_runs",
        sa.Column(
            "trigger_kind", sa.String(16), nullable=False, server_default="manual"
        ),
    )
    op.create_foreign_key(
        "fk_ingestion_run_schedule_project",
        "ingestion_runs",
        "ingestion_schedules",
        ["schedule_id", "project_id"],
        ["id", "project_id"],
    )
    op.create_check_constraint(
        "ck_ingestion_run_trigger_kind",
        "ingestion_runs",
        "trigger_kind IN ('manual','scheduled')",
    )
    op.create_check_constraint(
        "ck_ingestion_run_schedule_trigger",
        "ingestion_runs",
        "(trigger_kind = 'manual' AND schedule_id IS NULL) OR "
        "(trigger_kind = 'scheduled' AND schedule_id IS NOT NULL)",
    )
    op.create_foreign_key(
        "fk_ingestion_schedule_last_run_project",
        "ingestion_schedules",
        "ingestion_runs",
        ["last_run_id", "project_id"],
        ["id", "project_id"],
    )


def downgrade():
    op.drop_constraint(
        "fk_ingestion_schedule_last_run_project", "ingestion_schedules", type_="foreignkey"
    )
    op.drop_constraint(
        "ck_ingestion_run_schedule_trigger", "ingestion_runs", type_="check"
    )
    op.drop_constraint("ck_ingestion_run_trigger_kind", "ingestion_runs", type_="check")
    op.drop_constraint(
        "fk_ingestion_run_schedule_project", "ingestion_runs", type_="foreignkey"
    )
    op.drop_column("ingestion_runs", "trigger_kind")
    op.drop_column("ingestion_runs", "schedule_id")
    op.drop_index("ix_ingestion_schedule_due", table_name="ingestion_schedules")
    op.drop_index(
        "ix_ingestion_schedule_project_created", table_name="ingestion_schedules"
    )
    op.drop_table("ingestion_schedules")
