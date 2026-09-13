"""Add Notion source kinds.

Revision ID: 0015
Revises: 0014
"""

from alembic import op


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_document_origin_kind", "documents", type_="check")
    op.create_check_constraint(
        "ck_document_origin_kind",
        "documents",
        "origin_kind IN ('upload','website','s3','notion')",
    )
    op.drop_constraint("ck_source_item_kind", "source_items", type_="check")
    op.create_check_constraint(
        "ck_source_item_kind",
        "source_items",
        "kind IN ('website','s3','notion')",
    )


def downgrade():
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM source_items WHERE kind = 'notion')
               OR EXISTS (SELECT 1 FROM documents WHERE origin_kind = 'notion') THEN
                RAISE EXCEPTION
                    'Cannot downgrade 0015 while Notion ingestion history exists; '
                    'retain the migration or archive and explicitly remove that history first.';
            END IF;
        END
        $$
        """
    )
    op.drop_constraint("ck_source_item_kind", "source_items", type_="check")
    op.create_check_constraint(
        "ck_source_item_kind", "source_items", "kind IN ('website','s3')"
    )
    op.drop_constraint("ck_document_origin_kind", "documents", type_="check")
    op.create_check_constraint(
        "ck_document_origin_kind",
        "documents",
        "origin_kind IN ('upload','website','s3')",
    )
