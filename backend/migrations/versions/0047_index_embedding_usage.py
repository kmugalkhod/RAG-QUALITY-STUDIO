"""Record provider-reported embedding tokens and cost on each index version.

Spec 0007 (X8). Existing indexes keep NULL, which means unknown; new indexes
start at 0 and add each provider request's reported usage.
"""

import sqlalchemy as sa
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "index_versions", sa.Column("embedding_tokens", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "index_versions",
        sa.Column("embedding_cost_usd", sa.Numeric(14, 8), nullable=True),
    )
    op.alter_column("index_versions", "embedding_tokens", server_default="0")
    op.alter_column("index_versions", "embedding_cost_usd", server_default="0")


def downgrade():
    op.drop_column("index_versions", "embedding_cost_usd")
    op.drop_column("index_versions", "embedding_tokens")
