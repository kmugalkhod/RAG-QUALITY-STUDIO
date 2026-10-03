"""Page-level Website crawl checkpoints."""

from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE ingestion_runs "
        "ADD COLUMN crawl_state jsonb NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute(
        """
        CREATE TABLE website_crawl_frontier (
            id uuid PRIMARY KEY,
            run_id uuid NOT NULL,
            project_id uuid NOT NULL,
            source_node_id varchar(80) NOT NULL,
            ordinal integer NOT NULL,
            canonical_url varchar(4000),
            final_url varchar(4000),
            depth integer,
            lastmod timestamptz,
            status varchar(16) NOT NULL,
            attempts integer NOT NULL DEFAULT 0,
            reason varchar(500),
            error_code varchar(80),
            media_type varchar(200),
            size_bytes bigint,
            seen_again boolean NOT NULL DEFAULT false,
            original_url varchar(4000),
            duplicate_url varchar(4000),
            content_hash varchar(64),
            etag varchar(500),
            last_modified varchar(200),
            validator_unchanged boolean NOT NULL DEFAULT false,
            storage_name varchar(40),
            artifact_state varchar(24),
            artifact_encryption_schema integer,
            artifact_key_version varchar(32),
            artifact_wrapped_key bytea,
            artifact_wrap_nonce bytea,
            artifact_content_nonce bytea,
            source_item_id uuid,
            source_revision_id uuid,
            classification varchar(16),
            extracted_hash varchar(64),
            warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT fk_website_crawl_frontier_run_project
                FOREIGN KEY (run_id, project_id)
                REFERENCES ingestion_runs (id, project_id) ON DELETE CASCADE,
            CONSTRAINT uq_website_crawl_frontier_url
                UNIQUE (run_id, source_node_id, canonical_url),
            CONSTRAINT uq_website_crawl_frontier_ordinal
                UNIQUE (run_id, source_node_id, ordinal),
            CONSTRAINT ck_website_crawl_frontier_status CHECK (status IN
                ('queued','fetched','excluded','failed','duplicate','sitemap')),
            CONSTRAINT ck_website_crawl_frontier_attempts CHECK (attempts >= 0)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_website_crawl_frontier_status "
        "ON website_crawl_frontier (run_id, source_node_id, status, ordinal)"
    )


def downgrade():
    op.execute("DROP TABLE website_crawl_frontier")
    op.execute("ALTER TABLE ingestion_runs DROP COLUMN crawl_state")
