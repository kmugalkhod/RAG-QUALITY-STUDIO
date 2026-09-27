"""Add organization-owned answer deployments and immutable releases."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

U = sa.Uuid()
T = sa.DateTime(timezone=True)


def upgrade():
    op.create_unique_constraint(
        "uq_project_organization", "projects", ["id", "organization_id"]
    )
    op.create_unique_constraint(
        "uq_pipeline_version_identity",
        "pipeline_versions",
        ["id", "pipeline_id", "project_id"],
    )
    op.create_table(
        "answer_deployments",
        sa.Column("id", U, primary_key=True),
        sa.Column("organization_id", sa.String(100), nullable=False),
        sa.Column("project_id", U, nullable=False),
        sa.Column("pipeline_id", U, nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="paused"),
        sa.Column("active_release_id", U),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", U, nullable=False),
        sa.Column("created_at", T, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", T, nullable=False, server_default=sa.func.now()),
        sa.Column("archived_at", T),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            "project_id",
            "pipeline_id",
            name="uq_answer_deployment_identity",
        ),
        sa.UniqueConstraint(
            "id", "organization_id", "project_id", name="uq_answer_deployment_owner"
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "organization_id"],
            ["projects.id", "projects.organization_id"],
            name="fk_answer_deployment_project_org",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_id", "project_id"],
            ["pipelines.id", "pipelines.project_id"],
            name="fk_answer_deployment_pipeline_project",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 120",
            name="ck_answer_deployment_name",
        ),
        sa.CheckConstraint(
            "state IN ('paused','active','archived')", name="ck_answer_deployment_state"
        ),
        sa.CheckConstraint(
            "state != 'active' OR active_release_id IS NOT NULL",
            name="ck_answer_deployment_active_pointer",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_answer_deployment_revision"),
    )
    op.create_index(
        "ix_answer_deployment_org_project",
        "answer_deployments",
        ["organization_id", "project_id", "created_at", "id"],
    )
    op.create_table(
        "answer_deployment_releases",
        sa.Column("id", U, primary_key=True),
        sa.Column("deployment_id", U, nullable=False),
        sa.Column("organization_id", sa.String(100), nullable=False),
        sa.Column("project_id", U, nullable=False),
        sa.Column("pipeline_id", U, nullable=False),
        sa.Column("pipeline_version_id", U, nullable=False),
        sa.Column("index_id", U, nullable=False),
        sa.Column("release_number", sa.Integer(), nullable=False),
        sa.Column("execution", JSONB(), nullable=False),
        sa.Column("execution_sha256", sa.String(64), nullable=False),
        sa.Column("embedding_config", JSONB(), nullable=False),
        sa.Column("embedding_sha256", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column(
            "runtime_contract_version", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column("created_by", U, nullable=False),
        sa.Column("note", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", T, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "deployment_id", "release_number", name="uq_answer_release_number"
        ),
        sa.UniqueConstraint("id", "deployment_id", name="uq_answer_release_deployment"),
        sa.ForeignKeyConstraint(
            ["deployment_id", "organization_id", "project_id", "pipeline_id"],
            [
                "answer_deployments.id",
                "answer_deployments.organization_id",
                "answer_deployments.project_id",
                "answer_deployments.pipeline_id",
            ],
            name="fk_answer_release_deployment_identity",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_version_id", "pipeline_id", "project_id"],
            [
                "pipeline_versions.id",
                "pipeline_versions.pipeline_id",
                "pipeline_versions.project_id",
            ],
            name="fk_answer_release_pipeline_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["index_id", "project_id"],
            ["index_versions.id", "index_versions.project_id"],
            name="fk_answer_release_index_project",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("release_number >= 1", name="ck_answer_release_number"),
        sa.CheckConstraint("char_length(note) <= 500", name="ck_answer_release_note"),
    )
    op.create_index(
        "ix_answer_release_history",
        "answer_deployment_releases",
        ["deployment_id", "release_number"],
    )
    op.create_foreign_key(
        "fk_answer_deployment_active_release",
        "answer_deployments",
        "answer_deployment_releases",
        ["active_release_id", "id"],
        ["id", "deployment_id"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_table(
        "answer_deployment_events",
        sa.Column("id", U, primary_key=True),
        sa.Column("deployment_id", U, nullable=False),
        sa.Column("organization_id", sa.String(100), nullable=False),
        sa.Column("project_id", U, nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("actor_kind", sa.String(16), nullable=False),
        sa.Column("actor_id", U),
        sa.Column("old_release_id", U),
        sa.Column("new_release_id", U),
        sa.Column("request_id", sa.String(100)),
        sa.Column("reason", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", T, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["deployment_id", "organization_id", "project_id"],
            [
                "answer_deployments.id",
                "answer_deployments.organization_id",
                "answer_deployments.project_id",
            ],
            name="fk_answer_event_deployment_owner",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_answer_event_history",
        "answer_deployment_events",
        ["deployment_id", "created_at", "id"],
    )
    op.create_index(
        "ix_answer_event_org",
        "answer_deployment_events",
        ["organization_id", "created_at", "id"],
    )
    op.execute("""
    CREATE FUNCTION forbid_answer_release_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      RAISE EXCEPTION 'answer releases are immutable' USING ERRCODE = 'check_violation';
    END $$;
    """)
    op.execute("""
    CREATE TRIGGER answer_release_immutable BEFORE UPDATE OR DELETE
    ON answer_deployment_releases FOR EACH ROW EXECUTE FUNCTION forbid_answer_release_mutation()
    """)
    op.execute("""
    CREATE TRIGGER answer_event_immutable BEFORE UPDATE OR DELETE
    ON answer_deployment_events FOR EACH ROW EXECUTE FUNCTION forbid_answer_release_mutation()
    """)


def downgrade():
    connection = op.get_bind()
    for table in (
        "answer_deployment_events",
        "answer_deployment_releases",
        "answer_deployments",
    ):
        if connection.scalar(sa.text(f"SELECT count(*) FROM {table}")):
            raise RuntimeError(
                "Answer deployment data is retained. Roll back application code "
                "with the additive schema in place."
            )
    op.execute("DROP TRIGGER answer_event_immutable ON answer_deployment_events")
    op.execute("DROP TRIGGER answer_release_immutable ON answer_deployment_releases")
    op.execute("DROP FUNCTION forbid_answer_release_mutation()")
    op.drop_table("answer_deployment_events")
    op.drop_constraint(
        "fk_answer_deployment_active_release", "answer_deployments", type_="foreignkey"
    )
    op.drop_table("answer_deployment_releases")
    op.drop_table("answer_deployments")
    op.drop_constraint(
        "uq_pipeline_version_identity", "pipeline_versions", type_="unique"
    )
    op.drop_constraint("uq_project_organization", "projects", type_="unique")
