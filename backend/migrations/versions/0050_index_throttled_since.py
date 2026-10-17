"""When an index's embedding requests started being refused for rate limits.

Spec 0012 D7 (A9). A throttled batch waits without counting as a failure; after
15 minutes of continuous throttling the index fails with a clear message. NULL
means the index is not being throttled.
"""

import sqlalchemy as sa
from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "index_versions",
        sa.Column("throttled_since", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("index_versions", "throttled_since")
