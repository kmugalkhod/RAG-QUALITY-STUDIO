"""Add Confluence source kinds.

Revision ID: 0016
Revises: 0015
"""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_document_origin_kind", "documents", type_="check")
    op.create_check_constraint(
        "ck_document_origin_kind",
        "documents",
        "origin_kind IN ('upload','website','s3','notion','confluence')",
    )
    op.drop_constraint("ck_source_item_kind", "source_items", type_="check")
    op.create_check_constraint(
        "ck_source_item_kind",
        "source_items",
        "kind IN ('website','s3','notion','confluence')",
    )


def downgrade():
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM source_items WHERE kind = 'confluence')
               OR EXISTS (SELECT 1 FROM documents WHERE origin_kind = 'confluence') THEN
                RAISE EXCEPTION 'Cannot downgrade 0016 while Confluence ingestion history exists.';
            END IF;
        END $$
    """)
    op.drop_constraint("ck_source_item_kind", "source_items", type_="check")
    op.create_check_constraint(
        "ck_source_item_kind", "source_items", "kind IN ('website','s3','notion')"
    )
    op.drop_constraint("ck_document_origin_kind", "documents", type_="check")
    op.create_check_constraint(
        "ck_document_origin_kind",
        "documents",
        "origin_kind IN ('upload','website','s3','notion')",
    )
