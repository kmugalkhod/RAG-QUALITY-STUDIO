"""Indexed text hash for project-scoped embedding reuse."""

from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade():
    # The database owns the hash so every chunk writer stays consistent.
    op.execute("ALTER TABLE chunks ADD COLUMN embedding_text_hash bytea")
    op.execute(
        """
        CREATE FUNCTION chunks_embedding_text_hash() RETURNS trigger AS $$
        BEGIN
            NEW.embedding_text_hash := sha256(
                convert_to(coalesce(NEW.embedding_text, NEW.text), 'UTF8')
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER chunks_embedding_text_hash
        BEFORE INSERT OR UPDATE OF text, embedding_text ON chunks
        FOR EACH ROW EXECUTE FUNCTION chunks_embedding_text_hash()
        """
    )
    op.execute(
        "UPDATE chunks SET embedding_text_hash = "
        "sha256(convert_to(coalesce(embedding_text, text), 'UTF8'))"
    )
    op.create_index("ix_chunks_embedding_text_hash", "chunks", ["embedding_text_hash"])
    op.create_index(
        "ix_index_chunks_member", "index_chunks", ["run_id", "ordinal", "index_id"]
    )


def downgrade():
    op.drop_index("ix_index_chunks_member", table_name="index_chunks")
    op.drop_index("ix_chunks_embedding_text_hash", table_name="chunks")
    op.execute("DROP TRIGGER chunks_embedding_text_hash ON chunks")
    op.execute("DROP FUNCTION chunks_embedding_text_hash()")
    op.execute("ALTER TABLE chunks DROP COLUMN embedding_text_hash")
