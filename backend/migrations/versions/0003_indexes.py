"""Enable pgvector and add immutable index snapshots and batch checkpoints."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import VECTOR

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "index_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding_config", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("embedded_count", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("execution_token", sa.Uuid(), nullable=True),
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
        sa.UniqueConstraint("project_id", "version", name="uq_index_version"),
        sa.UniqueConstraint("id", "dimensions", name="uq_index_dimensions"),
        sa.CheckConstraint(
            "dimensions BETWEEN 1 AND 16000", name="ck_index_dimensions"
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_index_status",
        ),
        sa.CheckConstraint(
            "chunk_count > 0 AND embedded_count BETWEEN 0 AND chunk_count",
            name="ck_index_counts",
        ),
        sa.CheckConstraint(
            "status != 'succeeded' OR embedded_count = chunk_count",
            name="ck_index_complete",
        ),
        sa.CheckConstraint(
            "failures BETWEEN 0 AND 3 AND attempts >= 0", name="ck_index_attempts"
        ),
    )
    op.create_index(
        "ix_indexes_status_updated", "index_versions", ["status", "updated_at"]
    )
    op.create_index(
        "uq_index_active_project",
        "index_versions",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued','running')"),
    )
    op.create_table(
        "index_chunks",
        sa.Column("index_id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), primary_key=True),
        sa.Column("ordinal", sa.Integer(), primary_key=True),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding", VECTOR(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id", "ordinal"], ["chunks.run_id", "chunks.ordinal"]
        ),
        sa.ForeignKeyConstraint(
            ["index_id", "dimensions"],
            ["index_versions.id", "index_versions.dimensions"],
        ),
        sa.CheckConstraint(
            "embedding IS NULL OR vector_dims(embedding) = dimensions",
            name="ck_embedding_dimensions",
        ),
        sa.CheckConstraint(
            "embedding IS NULL OR vector_norm(embedding) > 0",
            name="ck_embedding_nonzero",
        ),
    )


def downgrade():
    op.drop_table("index_chunks")
    op.drop_table("index_versions")
    # Keep the extension: it may be used by other schemas in this database.
