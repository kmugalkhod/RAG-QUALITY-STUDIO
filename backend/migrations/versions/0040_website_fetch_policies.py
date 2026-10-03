"""Recorded effective Website fetch limits on source previews."""

from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE source_previews "
        "ADD COLUMN fetch_policies jsonb NOT NULL DEFAULT '{}'::jsonb"
    )


def downgrade():
    op.execute("ALTER TABLE source_previews DROP COLUMN fetch_policies")
