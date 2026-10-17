"""Partial index of index members that still need a vector.

Spec 0012 C6. Each embedding batch reads the next members whose embedding is
NULL; this index keeps that read small however many members already have a
vector. It holds only unembedded rows, so a finished index costs nothing.
"""

from alembic import op
import sqlalchemy as sa

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_index_chunks_unembedded",
        "index_chunks",
        ["index_id", "run_id", "ordinal"],
        postgresql_where=sa.text("embedding IS NULL"),
    )


def downgrade():
    op.drop_index("ix_index_chunks_unembedded", table_name="index_chunks")
