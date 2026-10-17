"""Bookkeeping warnings on ingestion runs.

Spec 0012 A6. Once a run's index is live the run is recorded as succeeded; a
problem after that point (for example updating stage states) is kept here
instead of failing the run. Existing runs get an empty list.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "ingestion_runs",
        sa.Column(
            "warnings",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade():
    op.drop_column("ingestion_runs", "warnings")
