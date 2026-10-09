"""Allow a 'skipped' status for website run items that were never indexed.

Spec 0007 (X7): links outside the source scope, repeated links and sitemaps were
shown as succeeded with 0 chunks. They now keep the status 'skipped'.
"""

from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE website_run_items DROP CONSTRAINT ck_website_run_item_status"
    )
    op.execute(
        "ALTER TABLE website_run_items ADD CONSTRAINT ck_website_run_item_status "
        "CHECK (status IN ('ready','succeeded','failed','cancelled','skipped'))"
    )


def downgrade():
    op.execute(
        "UPDATE website_run_items SET status = 'succeeded' WHERE status = 'skipped'"
    )
    op.execute(
        "ALTER TABLE website_run_items DROP CONSTRAINT ck_website_run_item_status"
    )
    op.execute(
        "ALTER TABLE website_run_items ADD CONSTRAINT ck_website_run_item_status "
        "CHECK (status IN ('ready','succeeded','failed','cancelled'))"
    )
