"""Count the vectors an index reused instead of requesting.

Spec 0012 Part B (the Embed panel's "N new, M reused"). Existing indexes keep
NULL, which means not recorded; new indexes start at 0.
"""

import sqlalchemy as sa
from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "index_versions",
        sa.Column("reused_vector_count", sa.Integer(), nullable=True),
    )
    op.alter_column("index_versions", "reused_vector_count", server_default="0")


def downgrade():
    op.drop_column("index_versions", "reused_vector_count")
