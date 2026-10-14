"""Recommended Website settings jobs and per-version settings provenance.

Spec 0011. `setting_recommendations` holds bounded probe results and the
settings code computed from them. `pipeline_versions.settings_provenance` is
written only when a version is inserted; existing versions stay NULL, which
means no recommendation was recorded. Downgrade drops both; saved `execution`
is never changed, so pipelines and runs are unaffected.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "setting_recommendations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("target", sa.String(16), nullable=False),
        sa.Column("source_node_id", sa.String(80), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("progress_step", sa.String(24), nullable=True),
        sa.Column("inputs", postgresql.JSONB(), nullable=False),
        sa.Column("inputs_hash", sa.String(64), nullable=False),
        sa.Column("probe_version", sa.String(32), nullable=False),
        sa.Column("rules_version", sa.String(32), nullable=False),
        sa.Column(
            "signals",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("recommended", postgresql.JSONB(), nullable=True),
        sa.Column(
            "fields",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "warnings",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("execution_token", sa.Uuid(), nullable=True),
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
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "target IN ('website')", name="ck_setting_recommendation_target"
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_setting_recommendation_status",
        ),
        sa.CheckConstraint(
            "progress BETWEEN 0 AND 100", name="ck_setting_recommendation_progress"
        ),
        sa.CheckConstraint(
            "status != 'succeeded' OR progress = 100",
            name="ck_setting_recommendation_complete",
        ),
        sa.CheckConstraint(
            "progress_step IS NULL OR progress_step IN "
            "('robots','start_page','sitemaps','sample_pages','validating')",
            name="ck_setting_recommendation_step",
        ),
        sa.CheckConstraint(
            "attempts BETWEEN 0 AND 10000 AND failures BETWEEN 0 AND 2",
            name="ck_setting_recommendation_attempts",
        ),
    )
    op.create_index(
        "ix_setting_recommendations_project_created",
        "setting_recommendations",
        ["project_id", "created_at", "id"],
    )
    op.create_index(
        "ix_setting_recommendations_status_dispatched",
        "setting_recommendations",
        ["status", "dispatched_at", "updated_at"],
    )
    op.create_index(
        "ix_setting_recommendations_project_hash",
        "setting_recommendations",
        ["project_id", "inputs_hash", "created_at"],
    )
    op.create_index(
        "uq_setting_recommendation_active_node",
        "setting_recommendations",
        ["project_id", "source_node_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued','running')"),
    )
    op.add_column(
        "pipeline_versions",
        sa.Column("settings_provenance", postgresql.JSONB(), nullable=True),
    )


def downgrade():
    op.drop_column("pipeline_versions", "settings_provenance")
    op.drop_index(
        "uq_setting_recommendation_active_node", table_name="setting_recommendations"
    )
    op.drop_index(
        "ix_setting_recommendations_project_hash", table_name="setting_recommendations"
    )
    op.drop_index(
        "ix_setting_recommendations_status_dispatched",
        table_name="setting_recommendations",
    )
    op.drop_index(
        "ix_setting_recommendations_project_created",
        table_name="setting_recommendations",
    )
    op.drop_table("setting_recommendations")
