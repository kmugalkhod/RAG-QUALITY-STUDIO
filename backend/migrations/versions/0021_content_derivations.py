"""Persist canonical document derivations and exact chunk lineage.

Revision ID: 0021
Revises: 0020
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "content_derivations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("processing_run_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("engine_version", sa.String(length=120), nullable=False),
        sa.Column("configuration_hash", sa.String(length=64), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("output_hash", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=1000)),
        sa.Column("media_type", sa.String(length=200), nullable=False),
        sa.Column(
            "measurements", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("findings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "transforms", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('extracted','cleaned')", name="ck_content_derivation_kind"
        ),
        sa.CheckConstraint("schema_version = 1", name="ck_content_derivation_schema"),
        sa.CheckConstraint(
            "char_length(configuration_hash) = 64 "
            "AND char_length(input_hash) = 64 AND char_length(output_hash) = 64",
            name="ck_content_derivation_hashes",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "project_id"],
            ["documents.id", "documents.project_id"],
            name="fk_content_derivation_document_project",
        ),
        sa.ForeignKeyConstraint(
            ["processing_run_id", "document_id"],
            ["processing_runs.id", "processing_runs.document_id"],
            name="fk_content_derivation_processing_document",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", name="uq_content_derivation_project"),
        sa.UniqueConstraint(
            "id", "processing_run_id", name="uq_content_derivation_processing"
        ),
        sa.UniqueConstraint(
            "id",
            "processing_run_id",
            "kind",
            name="uq_content_derivation_processing_kind",
        ),
        sa.UniqueConstraint(
            "processing_run_id", "kind", name="uq_content_derivation_kind"
        ),
    )
    op.create_index(
        "ix_content_derivations_project_run",
        "content_derivations",
        ["project_id", "processing_run_id", "kind"],
    )
    op.create_table(
        "content_blocks",
        sa.Column("derivation_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("block_id", sa.String(length=64), nullable=False),
        sa.Column("block_type", sa.String(length=24), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer()),
        sa.Column("bounding_box", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column(
            "heading_path", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "source_span", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.CheckConstraint("ordinal >= 0", name="ck_content_block_ordinal"),
        sa.CheckConstraint(
            "block_type IN ('title','heading','paragraph','list_item','table','code',"
            "'quote','image_caption','footnote','unknown')",
            name="ck_content_block_type",
        ),
        sa.CheckConstraint(
            "page_number IS NULL OR page_number > 0", name="ck_content_block_page"
        ),
        sa.ForeignKeyConstraint(
            ["derivation_id"],
            ["content_derivations.id"],
            name="fk_content_block_derivation",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("derivation_id", "ordinal"),
        sa.UniqueConstraint(
            "derivation_id", "block_id", name="uq_content_block_stable_id"
        ),
    )
    op.create_table(
        "chunk_block_spans",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_ordinal", sa.Integer(), nullable=False),
        sa.Column("span_ordinal", sa.Integer(), nullable=False),
        sa.Column("derivation_id", sa.Uuid(), nullable=False),
        sa.Column("derivation_kind", sa.String(length=16), nullable=False),
        sa.Column("block_ordinal", sa.Integer(), nullable=False),
        sa.Column("block_start_char", sa.Integer(), nullable=False),
        sa.Column("block_end_char", sa.Integer(), nullable=False),
        sa.Column("chunk_start_char", sa.Integer(), nullable=False),
        sa.Column("chunk_end_char", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "span_ordinal >= 0 AND block_ordinal >= 0",
            name="ck_chunk_block_span_ordinals",
        ),
        sa.CheckConstraint(
            "block_start_char >= 0 AND block_end_char > block_start_char "
            "AND chunk_start_char >= 0 AND chunk_end_char > chunk_start_char",
            name="ck_chunk_block_span_offsets",
        ),
        sa.CheckConstraint(
            "derivation_kind = 'cleaned'",
            name="ck_chunk_block_span_cleaned_derivation",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "chunk_ordinal"],
            ["chunks.run_id", "chunks.ordinal"],
            name="fk_chunk_block_span_chunk",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["derivation_id", "run_id", "derivation_kind"],
            [
                "content_derivations.id",
                "content_derivations.processing_run_id",
                "content_derivations.kind",
            ],
            name="fk_chunk_block_span_derivation_run",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["derivation_id", "block_ordinal"],
            ["content_blocks.derivation_id", "content_blocks.ordinal"],
            name="fk_chunk_block_span_block",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("run_id", "chunk_ordinal", "span_ordinal"),
    )
    op.create_index(
        "ix_chunk_block_spans_derivation",
        "chunk_block_spans",
        ["derivation_id", "block_ordinal"],
    )


def downgrade():
    op.drop_index("ix_chunk_block_spans_derivation", table_name="chunk_block_spans")
    op.drop_table("chunk_block_spans")
    op.drop_table("content_blocks")
    op.drop_index(
        "ix_content_derivations_project_run", table_name="content_derivations"
    )
    op.drop_table("content_derivations")
