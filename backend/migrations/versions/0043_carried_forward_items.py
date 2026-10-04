"""Carried-forward Website run items for multi-source runs."""

from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE website_run_items "
        "DROP CONSTRAINT ck_website_run_item_outcome, "
        "ADD CONSTRAINT ck_website_run_item_outcome CHECK (outcome IN "
        "('new','changed','unchanged','removed','excluded','duplicate','failed',"
        "'sitemap','carried_forward'))"
    )
    op.execute(
        "ALTER TABLE source_snapshots "
        "ADD COLUMN carried_forward_count integer NOT NULL DEFAULT 0, "
        "ADD CONSTRAINT ck_source_snapshot_carried_forward "
        "CHECK (carried_forward_count >= 0)"
    )


def downgrade():
    # Carried items record which earlier pages a run kept; without the outcome
    # they cannot be represented, so a downgrade removes them.
    op.execute("DELETE FROM website_run_items WHERE outcome = 'carried_forward'")
    op.execute(
        "ALTER TABLE website_run_items "
        "DROP CONSTRAINT ck_website_run_item_outcome, "
        "ADD CONSTRAINT ck_website_run_item_outcome CHECK (outcome IN "
        "('new','changed','unchanged','removed','excluded','duplicate','failed','sitemap'))"
    )
    op.execute(
        "ALTER TABLE source_snapshots "
        "DROP CONSTRAINT ck_source_snapshot_carried_forward, "
        "DROP COLUMN carried_forward_count"
    )
