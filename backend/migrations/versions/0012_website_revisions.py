"""Add immutable website revisions and index provenance."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "documents",
        sa.Column(
            "origin_kind", sa.String(16), nullable=False, server_default="upload"
        ),
    )
    op.alter_column(
        "source_preview_items",
        "external_id",
        existing_type=sa.String(1000),
        type_=sa.String(4000),
        existing_nullable=True,
    )
    op.create_check_constraint(
        "ck_document_origin_kind",
        "documents",
        "origin_kind IN ('upload','website')",
    )
    op.add_column(
        "chunks",
        sa.Column(
            "provenance",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.drop_constraint("ck_ingestion_run_stage", "ingestion_runs", type_="check")
    op.drop_constraint("ck_ingestion_run_counts", "ingestion_runs", type_="check")
    op.create_check_constraint(
        "ck_ingestion_run_stage",
        "ingestion_runs",
        "stage IN ('discovering','processing','indexing','complete')",
    )
    op.create_check_constraint(
        "ck_ingestion_run_counts",
        "ingestion_runs",
        "discovered_count BETWEEN 0 AND 50000 "
        "AND processed_count BETWEEN 0 AND discovered_count "
        "AND failed_count BETWEEN 0 AND discovered_count "
        "AND processed_count + failed_count <= discovered_count "
        "AND chunk_count >= 0 AND embedded_count BETWEEN 0 AND chunk_count "
        "AND published_count BETWEEN 0 AND 1",
    )

    op.create_table(
        "source_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(4000), nullable=False),
        sa.Column("identity_hash", sa.String(64), nullable=False),
        sa.Column("canonical_location", sa.String(4000), nullable=False),
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
        sa.UniqueConstraint("id", "project_id", name="uq_source_item_project"),
        sa.UniqueConstraint(
            "project_id", "kind", "identity_hash", name="uq_source_item_identity"
        ),
        sa.CheckConstraint("kind = 'website'", name="ck_source_item_kind"),
        sa.CheckConstraint(
            "char_length(identity_hash) = 64", name="ck_source_item_hash"
        ),
    )
    op.create_index(
        "ix_source_items_project_kind",
        "source_items",
        ["project_id", "kind", "updated_at"],
    )
    op.create_table(
        "source_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_item_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("processing_run_id", sa.Uuid(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("extracted_hash", sa.String(64), nullable=False),
        sa.Column("media_type", sa.String(200), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("artifact_storage_name", sa.String(40), nullable=False, unique=True),
        sa.Column("etag", sa.String(500), nullable=True),
        sa.Column("last_modified", sa.String(200), nullable=True),
        sa.Column("provider_revision", sa.String(500), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("extraction_config", postgresql.JSONB(), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("id", "project_id", name="uq_source_revision_project"),
        sa.UniqueConstraint(
            "source_item_id", "content_hash", name="uq_source_revision_content"
        ),
        sa.UniqueConstraint("document_id", name="uq_source_revision_document"),
        sa.UniqueConstraint("processing_run_id", name="uq_source_revision_processing"),
        sa.ForeignKeyConstraint(
            ["source_item_id", "project_id"],
            ["source_items.id", "source_items.project_id"],
            name="fk_source_revision_item_project",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "project_id"],
            ["documents.id", "documents.project_id"],
            name="fk_source_revision_document_project",
        ),
        sa.ForeignKeyConstraint(
            ["processing_run_id", "document_id"],
            ["processing_runs.id", "processing_runs.document_id"],
            name="fk_source_revision_processing_document",
        ),
        sa.CheckConstraint(
            "char_length(content_hash) = 64", name="ck_source_revision_hash"
        ),
        sa.CheckConstraint(
            "char_length(extracted_hash) = 64",
            name="ck_source_revision_extracted_hash",
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_source_revision_size"),
    )
    op.create_index(
        "ix_source_revisions_item_fetched",
        "source_revisions",
        ["source_item_id", "fetched_at", "id"],
    )
    op.create_table(
        "website_run_items",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_node_id", sa.String(80), nullable=False),
        sa.Column("source_item_id", sa.Uuid(), nullable=True),
        sa.Column("source_revision_id", sa.Uuid(), nullable=True),
        sa.Column("canonical_location", sa.String(4000), nullable=True),
        sa.Column("display_name", sa.String(500), nullable=False),
        sa.Column("media_type", sa.String(200), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
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
        sa.PrimaryKeyConstraint("run_id", "ordinal"),
        sa.ForeignKeyConstraint(
            ["run_id", "project_id"],
            ["ingestion_runs.id", "ingestion_runs.project_id"],
            name="fk_website_run_item_run_project",
        ),
        sa.ForeignKeyConstraint(
            ["source_item_id", "project_id"],
            ["source_items.id", "source_items.project_id"],
            name="fk_website_run_item_source_project",
        ),
        sa.ForeignKeyConstraint(
            ["source_revision_id", "project_id"],
            ["source_revisions.id", "source_revisions.project_id"],
            name="fk_website_run_item_revision_project",
        ),
        sa.CheckConstraint(
            "outcome IN ('new','changed','unchanged','removed','excluded','duplicate','failed')",
            name="ck_website_run_item_outcome",
        ),
        sa.CheckConstraint(
            "status IN ('ready','succeeded','failed','cancelled')",
            name="ck_website_run_item_status",
        ),
        sa.CheckConstraint("chunk_count >= 0", name="ck_website_run_item_chunks"),
    )
    op.create_index(
        "ix_website_run_items_status",
        "website_run_items",
        ["run_id", "status", "ordinal"],
    )
    op.create_table(
        "index_source_revisions",
        sa.Column("index_id", sa.Uuid(), nullable=False),
        sa.Column("source_revision_id", sa.Uuid(), nullable=False),
        sa.Column("source_item_id", sa.Uuid(), nullable=False),
        sa.Column("source_node_id", sa.String(80), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("index_id", "source_revision_id"),
        sa.ForeignKeyConstraint(
            ["index_id", "project_id"],
            ["index_versions.id", "index_versions.project_id"],
            name="fk_index_source_revision_index_project",
        ),
        sa.ForeignKeyConstraint(
            ["source_revision_id", "project_id"],
            ["source_revisions.id", "source_revisions.project_id"],
            name="fk_index_source_revision_revision_project",
        ),
        sa.ForeignKeyConstraint(
            ["source_item_id", "project_id"],
            ["source_items.id", "source_items.project_id"],
            name="fk_index_source_revision_item_project",
        ),
        sa.UniqueConstraint("index_id", "source_item_id", name="uq_index_source_item"),
    )
    op.create_index(
        "ix_index_source_revisions_item",
        "index_source_revisions",
        ["source_item_id", "index_id"],
    )


def downgrade():
    op.drop_index("ix_index_source_revisions_item", table_name="index_source_revisions")
    op.drop_table("index_source_revisions")
    op.drop_index("ix_website_run_items_status", table_name="website_run_items")
    op.drop_table("website_run_items")
    op.drop_index("ix_source_revisions_item_fetched", table_name="source_revisions")
    op.drop_table("source_revisions")
    op.drop_index("ix_source_items_project_kind", table_name="source_items")
    op.drop_table("source_items")
    op.drop_constraint("ck_ingestion_run_counts", "ingestion_runs", type_="check")
    op.drop_constraint("ck_ingestion_run_stage", "ingestion_runs", type_="check")
    op.create_check_constraint(
        "ck_ingestion_run_stage",
        "ingestion_runs",
        "stage IN ('processing','indexing','complete')",
    )
    op.create_check_constraint(
        "ck_ingestion_run_counts",
        "ingestion_runs",
        "discovered_count BETWEEN 1 AND 1000 "
        "AND processed_count BETWEEN 0 AND discovered_count "
        "AND failed_count BETWEEN 0 AND discovered_count "
        "AND processed_count + failed_count <= discovered_count "
        "AND chunk_count >= 0 AND embedded_count BETWEEN 0 AND chunk_count "
        "AND published_count BETWEEN 0 AND 1",
    )
    op.drop_column("chunks", "provenance")
    op.drop_constraint("ck_document_origin_kind", "documents", type_="check")
    op.drop_column("documents", "origin_kind")
    op.alter_column(
        "source_preview_items",
        "external_id",
        existing_type=sa.String(4000),
        type_=sa.String(1000),
        existing_nullable=True,
    )
