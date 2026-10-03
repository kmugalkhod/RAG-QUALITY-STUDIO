"""Website request attempts, item warnings and nested-sitemap outcomes."""

from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE source_preview_items ADD COLUMN attempts integer NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE source_preview_items "
        "DROP CONSTRAINT ck_source_preview_item_status, "
        "ADD CONSTRAINT ck_source_preview_item_status "
        "CHECK (status IN ('included','excluded','duplicate','failed','sitemap'))"
    )
    op.execute(
        "ALTER TABLE website_run_items "
        "ADD COLUMN attempts integer NOT NULL DEFAULT 0, "
        "ADD COLUMN warnings jsonb NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute(
        "ALTER TABLE website_run_items "
        "DROP CONSTRAINT ck_website_run_item_outcome, "
        "ADD CONSTRAINT ck_website_run_item_outcome CHECK (outcome IN "
        "('new','changed','unchanged','removed','excluded','duplicate','failed','sitemap'))"
    )


def downgrade():
    op.execute("DELETE FROM website_run_items WHERE outcome = 'sitemap'")
    op.execute("DELETE FROM source_preview_items WHERE status = 'sitemap'")
    op.execute(
        "ALTER TABLE website_run_items "
        "DROP CONSTRAINT ck_website_run_item_outcome, "
        "ADD CONSTRAINT ck_website_run_item_outcome CHECK (outcome IN "
        "('new','changed','unchanged','removed','excluded','duplicate','failed')), "
        "DROP COLUMN warnings, DROP COLUMN attempts"
    )
    op.execute(
        "ALTER TABLE source_preview_items "
        "DROP CONSTRAINT ck_source_preview_item_status, "
        "ADD CONSTRAINT ck_source_preview_item_status "
        "CHECK (status IN ('included','excluded','duplicate','failed')), "
        "DROP COLUMN attempts"
    )
