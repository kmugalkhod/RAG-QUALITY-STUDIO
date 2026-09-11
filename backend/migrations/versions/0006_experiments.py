"""Immutable datasets and durable experiment checkpoints."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_query_project", "query_runs", ["id", "project_id"])
    op.create_table(
        "datasets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.UniqueConstraint("id", "project_id", name="uq_dataset_project"),
    )
    op.create_index("ix_datasets_project_id", "datasets", ["project_id"])
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("rows", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "project_id"], ["datasets.id", "datasets.project_id"]
        ),
        sa.UniqueConstraint("dataset_id", "version", name="uq_dataset_version"),
        sa.UniqueConstraint("id", "project_id", name="uq_dataset_version_project"),
    )
    op.create_index(
        "ix_dataset_versions_project_id", "dataset_versions", ["project_id"]
    )
    op.create_table(
        "experiments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("execution_token", sa.Uuid()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("dispatched_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.String()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id", "project_id"],
            ["dataset_versions.id", "dataset_versions.project_id"],
        ),
        sa.UniqueConstraint("id", "project_id", name="uq_experiment_project"),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_experiment_status",
        ),
    )
    op.create_index(
        "ix_experiment_project_created", "experiments", ["project_id", "created_at"]
    )
    op.create_table(
        "experiment_items",
        sa.Column("experiment_id", sa.Uuid(), primary_key=True),
        sa.Column("candidate", sa.Integer(), primary_key=True),
        sa.Column("ordinal", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_version_id", sa.Uuid(), nullable=False),
        sa.Column("query_run_id", sa.Uuid()),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("output", JSONB(), nullable=False),
        sa.Column("metrics", JSONB(), nullable=False),
        sa.Column("error", sa.String()),
        sa.ForeignKeyConstraint(
            ["experiment_id", "project_id"],
            ["experiments.id", "experiments.project_id"],
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_version_id", "project_id"],
            ["pipeline_versions.id", "pipeline_versions.project_id"],
        ),
        sa.ForeignKeyConstraint(
            ["query_run_id", "project_id"], ["query_runs.id", "query_runs.project_id"]
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','succeeded','failed','skipped')",
            name="ck_experiment_item_status",
        ),
    )


def downgrade():
    for table in ["experiment_items", "experiments", "dataset_versions", "datasets"]:
        op.drop_table(table)
    op.drop_constraint("uq_query_project", "query_runs", type_="unique")
