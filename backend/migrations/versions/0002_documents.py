"""Add immutable document uploads, processing versions and complete chunk sets."""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("storage_name", sa.String(40), nullable=False, unique=True),
        sa.Column("media_type", sa.String(32), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_document_size"),
    )
    op.create_index(
        "ix_documents_project_created", "documents", ["project_id", "created_at", "id"]
    )
    op.create_table(
        "processing_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_id", sa.Uuid(), sa.ForeignKey("documents.id"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("chunk_size", sa.Integer(), nullable=False),
        sa.Column("overlap", sa.Integer(), nullable=False),
        sa.Column("config_version", sa.String(32), nullable=False),
        sa.Column("parser_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("execution_token", sa.Uuid(), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
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
        sa.UniqueConstraint("document_id", "version", name="uq_run_version"),
        sa.CheckConstraint(
            "chunk_size > 0 AND overlap >= 0 AND overlap < chunk_size",
            name="ck_run_chunking",
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_run_status",
        ),
        sa.CheckConstraint("attempts BETWEEN 0 AND 3", name="ck_run_attempts"),
    )
    op.create_index(
        "ix_runs_status_updated", "processing_runs", ["status", "updated_at"]
    )
    op.create_index(
        "uq_run_active_document",
        "processing_runs",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued','running')"),
    )
    op.create_table(
        "chunks",
        sa.Column(
            "run_id", sa.Uuid(), sa.ForeignKey("processing_runs.id"), primary_key=True
        ),
        sa.Column("ordinal", sa.Integer(), primary_key=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "start_char >= 0 AND end_char > start_char", name="ck_chunk_offsets"
        ),
    )


def downgrade():
    op.drop_table("chunks")
    op.drop_table("processing_runs")
    op.drop_table("documents")
