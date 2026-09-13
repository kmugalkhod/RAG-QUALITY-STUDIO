"""Add S3 source and configuration-versioned revisions.

Revision ID: 0014
Revises: 0013
"""

from alembic import op
import sqlalchemy as sa


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "source_preview_items",
        sa.Column("provider_revision", sa.String(1000), nullable=True),
    )
    op.alter_column(
        "source_revisions",
        "provider_revision",
        existing_type=sa.String(500),
        type_=sa.String(1000),
        existing_nullable=True,
    )
    op.drop_constraint("ck_document_origin_kind", "documents", type_="check")
    op.create_check_constraint(
        "ck_document_origin_kind",
        "documents",
        "origin_kind IN ('upload','website','s3')",
    )
    op.drop_constraint("ck_source_item_kind", "source_items", type_="check")
    op.create_check_constraint(
        "ck_source_item_kind", "source_items", "kind IN ('website','s3')"
    )
    op.add_column(
        "source_revisions",
        sa.Column(
            "processing_config_hash",
            sa.String(64),
            nullable=False,
            server_default="0000000000000000000000000000000000000000000000000000000000000000",
        ),
    )
    op.drop_constraint("uq_source_revision_content", "source_revisions", type_="unique")
    op.create_unique_constraint(
        "uq_source_revision_content",
        "source_revisions",
        ["source_item_id", "content_hash", "processing_config_hash"],
    )
    op.create_check_constraint(
        "ck_source_revision_processing_hash",
        "source_revisions",
        "char_length(processing_config_hash) = 64",
    )
    op.alter_column("source_revisions", "processing_config_hash", server_default=None)


def downgrade():
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM source_items WHERE kind = 's3')
               OR EXISTS (SELECT 1 FROM documents WHERE origin_kind = 's3') THEN
                RAISE EXCEPTION
                    'Cannot downgrade 0014 while S3 ingestion history exists; '
                    'retain the migration or archive and explicitly remove that history first.';
            END IF;
        END
        $$
        """
    )
    op.drop_constraint("uq_source_revision_content", "source_revisions", type_="unique")
    op.drop_constraint(
        "ck_source_revision_processing_hash", "source_revisions", type_="check"
    )
    op.create_unique_constraint(
        "uq_source_revision_content",
        "source_revisions",
        ["source_item_id", "content_hash"],
    )
    op.drop_column("source_revisions", "processing_config_hash")
    op.alter_column(
        "source_revisions",
        "provider_revision",
        existing_type=sa.String(1000),
        type_=sa.String(500),
        existing_nullable=True,
    )
    op.drop_column("source_preview_items", "provider_revision")
    op.drop_constraint("ck_source_item_kind", "source_items", type_="check")
    op.create_check_constraint(
        "ck_source_item_kind", "source_items", "kind = 'website'"
    )
    op.drop_constraint("ck_document_origin_kind", "documents", type_="check")
    op.create_check_constraint(
        "ck_document_origin_kind",
        "documents",
        "origin_kind IN ('upload','website')",
    )
