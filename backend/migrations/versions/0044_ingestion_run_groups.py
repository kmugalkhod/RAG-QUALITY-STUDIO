"""Run groups for one-index-per-source ingestion pipelines."""

from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE ingestion_run_groups (
            id uuid PRIMARY KEY,
            project_id uuid NOT NULL REFERENCES projects(id),
            pipeline_version_id uuid NOT NULL,
            schedule_id uuid,
            trigger_kind varchar(16) NOT NULL DEFAULT 'manual',
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_ingestion_run_group_project UNIQUE (id, project_id),
            CONSTRAINT fk_ingestion_run_group_pipeline_project
                FOREIGN KEY (pipeline_version_id, project_id)
                REFERENCES pipeline_versions (id, project_id),
            CONSTRAINT fk_ingestion_run_group_schedule_project
                FOREIGN KEY (schedule_id, project_id)
                REFERENCES ingestion_schedules (id, project_id),
            CONSTRAINT ck_ingestion_run_group_trigger_kind
                CHECK (trigger_kind IN ('manual','scheduled'))
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_ingestion_run_groups_version_created "
        "ON ingestion_run_groups (project_id, pipeline_version_id, created_at)"
    )
    op.execute(
        "ALTER TABLE ingestion_runs "
        "ADD COLUMN group_id uuid, "
        "ADD COLUMN branch_source_node_id varchar(80), "
        "ADD CONSTRAINT fk_ingestion_run_group_project "
        "FOREIGN KEY (group_id, project_id) "
        "REFERENCES ingestion_run_groups (id, project_id), "
        "ADD CONSTRAINT ck_ingestion_run_group_branch "
        "CHECK ((group_id IS NULL) = (branch_source_node_id IS NULL))"
    )
    op.execute("CREATE INDEX ix_ingestion_runs_group ON ingestion_runs (group_id)")


def downgrade():
    # Branch runs stay as ordinary runs; only their grouping is removed.
    op.execute("DROP INDEX ix_ingestion_runs_group")
    op.execute(
        "ALTER TABLE ingestion_runs "
        "DROP CONSTRAINT ck_ingestion_run_group_branch, "
        "DROP CONSTRAINT fk_ingestion_run_group_project, "
        "DROP COLUMN branch_source_node_id, "
        "DROP COLUMN group_id"
    )
    op.execute("DROP TABLE ingestion_run_groups")
