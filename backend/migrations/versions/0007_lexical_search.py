"""Index immutable chunk text for keyword retrieval.

Revision ID: 0007
Revises: 0006
"""

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_chunks_lexical",
        "chunks",
        [sa.text("to_tsvector('simple'::regconfig, text)")],
        postgresql_using="gin",
    )


def downgrade():
    op.drop_index("ix_chunks_lexical", table_name="chunks")
