"""Persist single-turn answer runs and exact evidence snapshots."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        "uq_index_project", "index_versions", ["id", "project_id"]
    )
    op.create_table(
        "query_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("index_id", sa.Uuid(), nullable=False),
        sa.Column("index_version", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text()),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["index_id", "project_id"],
            ["index_versions.id", "index_versions.project_id"],
        ),
        sa.CheckConstraint(
            "status IN ('running','succeeded','insufficient_evidence','failed')",
            name="ck_query_status",
        ),
    )
    op.create_index(
        "ix_query_project_created", "query_runs", ["project_id", "created_at"]
    )


def downgrade():
    op.drop_table("query_runs")
    op.drop_constraint("uq_index_project", "index_versions", type_="unique")
