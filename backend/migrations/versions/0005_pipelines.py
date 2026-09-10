"""Project pipelines, immutable versions and query run references."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pipelines",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("id", "project_id", name="uq_pipeline_project"),
    )
    op.create_index(
        "ix_pipeline_project_created", "pipelines", ["project_id", "created_at"]
    )
    op.create_table(
        "pipeline_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("pipeline_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("execution", JSONB(), nullable=False),
        sa.Column("layout", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_id", "project_id"], ["pipelines.id", "pipelines.project_id"]
        ),
        sa.UniqueConstraint("pipeline_id", "version", name="uq_pipeline_version"),
        sa.UniqueConstraint("id", "project_id", name="uq_pipeline_version_project"),
    )
    op.add_column("query_runs", sa.Column("pipeline_version_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_query_pipeline_version",
        "query_runs",
        "pipeline_versions",
        ["pipeline_version_id", "project_id"],
        ["id", "project_id"],
    )


def downgrade():
    op.drop_constraint("fk_query_pipeline_version", "query_runs", type_="foreignkey")
    op.drop_column("query_runs", "pipeline_version_id")
    op.drop_table("pipeline_versions")
    op.drop_table("pipelines")
