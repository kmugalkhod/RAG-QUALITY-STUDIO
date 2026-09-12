"""Add answer and ingestion pipeline kinds."""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("pipelines", sa.Column("kind", sa.String(length=20), nullable=True))
    op.execute("UPDATE pipelines SET kind = 'answer'")
    op.alter_column("pipelines", "kind", nullable=False)
    op.create_check_constraint(
        "ck_pipeline_kind", "pipelines", "kind IN ('answer', 'ingestion')"
    )
    op.create_index(
        "ix_pipeline_project_kind_created",
        "pipelines",
        ["project_id", "kind", "created_at"],
    )


def downgrade():
    op.drop_index("ix_pipeline_project_kind_created", table_name="pipelines")
    op.drop_constraint("ck_pipeline_kind", "pipelines", type_="check")
    op.drop_column("pipelines", "kind")
