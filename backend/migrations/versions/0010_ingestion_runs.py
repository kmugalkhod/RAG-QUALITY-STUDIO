"""Add durable existing-files ingestion runs and explicit provenance."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        "uq_document_project", "documents", ["id", "project_id"]
    )
    op.create_unique_constraint(
        "uq_processing_run_document", "processing_runs", ["id", "document_id"]
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_version_id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_set_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("stage", sa.String(24), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("discovered_count", sa.Integer(), nullable=False),
        sa.Column("processed_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("embedded_count", sa.Integer(), nullable=False),
        sa.Column("published_count", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("execution_token", sa.Uuid(), nullable=True),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(
            ["pipeline_version_id", "project_id"],
            ["pipeline_versions.id", "pipeline_versions.project_id"],
            name="fk_ingestion_run_pipeline_project",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_set_id", "project_id"],
            ["knowledge_sets.id", "knowledge_sets.project_id"],
            name="fk_ingestion_run_knowledge_set_project",
        ),
        sa.UniqueConstraint("id", "project_id", name="uq_ingestion_run_project"),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_ingestion_run_status",
        ),
        sa.CheckConstraint(
            "stage IN ('processing','indexing','complete')",
            name="ck_ingestion_run_stage",
        ),
        sa.CheckConstraint(
            "progress BETWEEN 0 AND 100", name="ck_ingestion_run_progress"
        ),
        sa.CheckConstraint(
            "discovered_count BETWEEN 1 AND 1000 "
            "AND processed_count BETWEEN 0 AND discovered_count "
            "AND failed_count BETWEEN 0 AND discovered_count "
            "AND processed_count + failed_count <= discovered_count "
            "AND chunk_count >= 0 AND embedded_count BETWEEN 0 AND chunk_count "
            "AND published_count BETWEEN 0 AND 1",
            name="ck_ingestion_run_counts",
        ),
        sa.CheckConstraint(
            "attempts BETWEEN 0 AND 10000 AND failures BETWEEN 0 AND 3",
            name="ck_ingestion_run_attempts",
        ),
        sa.CheckConstraint(
            "status != 'succeeded' OR "
            "(stage = 'complete' AND progress = 100 AND published_count = 1 "
            "AND processed_count = discovered_count AND failed_count = 0 "
            "AND embedded_count = chunk_count)",
            name="ck_ingestion_run_complete",
        ),
    )
    op.create_index(
        "ix_ingestion_runs_project_created",
        "ingestion_runs",
        ["project_id", "created_at", "id"],
    )
    op.create_index(
        "ix_ingestion_runs_status_dispatched",
        "ingestion_runs",
        ["status", "dispatched_at", "updated_at"],
    )
    op.create_index(
        "uq_ingestion_active_knowledge_set",
        "ingestion_runs",
        ["knowledge_set_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued','running')"),
    )

    op.create_table(
        "ingestion_run_items",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("source_node_id", sa.String(80), nullable=False),
        sa.Column("processing_run_id", sa.Uuid(), nullable=False),
        sa.Column("processing_created", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("run_id", "document_id"),
        sa.ForeignKeyConstraint(
            ["run_id", "project_id"],
            ["ingestion_runs.id", "ingestion_runs.project_id"],
            name="fk_ingestion_item_run_project",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "project_id"],
            ["documents.id", "documents.project_id"],
            name="fk_ingestion_item_document_project",
        ),
        sa.ForeignKeyConstraint(
            ["processing_run_id", "document_id"],
            ["processing_runs.id", "processing_runs.document_id"],
            name="fk_ingestion_item_processing_document",
        ),
        sa.CheckConstraint(
            "status IN ('processing','ready','succeeded','failed','cancelled')",
            name="ck_ingestion_item_status",
        ),
        sa.CheckConstraint("chunk_count >= 0", name="ck_ingestion_item_chunks"),
    )
    op.create_index(
        "ix_ingestion_items_run_status",
        "ingestion_run_items",
        ["run_id", "status", "document_id"],
    )

    op.add_column(
        "index_versions", sa.Column("ingestion_run_id", sa.Uuid(), nullable=True)
    )
    op.create_unique_constraint(
        "uq_index_ingestion_run", "index_versions", ["ingestion_run_id"]
    )
    op.create_foreign_key(
        "fk_index_ingestion_run_project",
        "index_versions",
        "ingestion_runs",
        ["ingestion_run_id", "project_id"],
        ["id", "project_id"],
    )


def downgrade():
    op.drop_constraint(
        "fk_index_ingestion_run_project", "index_versions", type_="foreignkey"
    )
    op.drop_constraint("uq_index_ingestion_run", "index_versions", type_="unique")
    op.drop_column("index_versions", "ingestion_run_id")
    op.drop_index("ix_ingestion_items_run_status", table_name="ingestion_run_items")
    op.drop_table("ingestion_run_items")
    op.drop_index("uq_ingestion_active_knowledge_set", table_name="ingestion_runs")
    op.drop_index("ix_ingestion_runs_status_dispatched", table_name="ingestion_runs")
    op.drop_index("ix_ingestion_runs_project_created", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
    op.drop_constraint("uq_processing_run_document", "processing_runs", type_="unique")
    op.drop_constraint("uq_document_project", "documents", type_="unique")
