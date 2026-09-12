"""Add durable asynchronous source previews."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_previews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("discovered_count", sa.Integer(), nullable=False),
        sa.Column("included_count", sa.Integer(), nullable=False),
        sa.Column("excluded_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("execution_token", sa.Uuid(), nullable=True),
        sa.Column("execution", postgresql.JSONB(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
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
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("id", "project_id", name="uq_source_preview_project"),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_source_preview_status",
        ),
        sa.CheckConstraint(
            "progress BETWEEN 0 AND 100", name="ck_source_preview_progress"
        ),
        sa.CheckConstraint(
            "discovered_count >= 0 AND included_count >= 0 "
            "AND excluded_count >= 0 AND duplicate_count >= 0 "
            "AND failed_count >= 0 AND included_count + excluded_count + "
            "duplicate_count + failed_count = discovered_count",
            name="ck_source_preview_counts",
        ),
        sa.CheckConstraint(
            "attempts BETWEEN 0 AND 10000 AND failures BETWEEN 0 AND 3",
            name="ck_source_preview_attempts",
        ),
        sa.CheckConstraint(
            "status != 'succeeded' OR progress = 100", name="ck_source_preview_complete"
        ),
    )
    op.create_index(
        "ix_source_previews_project_created",
        "source_previews",
        ["project_id", "created_at", "id"],
    )
    op.create_index(
        "ix_source_previews_status_dispatched",
        "source_previews",
        ["status", "dispatched_at", "updated_at"],
    )
    op.create_index(
        "uq_source_preview_active_project",
        "source_previews",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued','running')"),
    )
    op.create_table(
        "source_preview_items",
        sa.Column("preview_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("source_node_id", sa.String(80), nullable=False),
        sa.Column("external_id", sa.String(1000), nullable=True),
        sa.Column("display_name", sa.String(500), nullable=False),
        sa.Column("canonical_location", sa.String(4000), nullable=True),
        sa.Column("media_type", sa.String(200), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("depth", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("preview_id", "ordinal"),
        sa.ForeignKeyConstraint(
            ["preview_id"], ["source_previews.id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "status IN ('included','excluded','duplicate','failed')",
            name="ck_source_preview_item_status",
        ),
        sa.CheckConstraint("ordinal >= 0", name="ck_source_preview_item_ordinal"),
        sa.CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0", name="ck_source_preview_item_size"
        ),
    )
    op.create_index(
        "ix_source_preview_items_status",
        "source_preview_items",
        ["preview_id", "status", "ordinal"],
    )


def downgrade():
    op.drop_index("ix_source_preview_items_status", table_name="source_preview_items")
    op.drop_table("source_preview_items")
    op.drop_index("uq_source_preview_active_project", table_name="source_previews")
    op.drop_index("ix_source_previews_status_dispatched", table_name="source_previews")
    op.drop_index("ix_source_previews_project_created", table_name="source_previews")
    op.drop_table("source_previews")
