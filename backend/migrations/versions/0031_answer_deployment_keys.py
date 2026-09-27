"""Add one-time hashed deployment credentials."""

from alembic import op
import sqlalchemy as sa

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "answer_deployment_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("deployment_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.String(100), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("prefix", sa.String(40), nullable=False),
        sa.Column("secret_hash", sa.String(64), nullable=False),
        sa.Column("pepper_version", sa.String(40), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("rotation_of_key_id", sa.Uuid()),
        sa.ForeignKeyConstraint(
            ["deployment_id", "organization_id", "project_id"],
            [
                "answer_deployments.id",
                "answer_deployments.organization_id",
                "answer_deployments.project_id",
            ],
            name="fk_answer_key_deployment_owner",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("prefix", name="uq_answer_key_prefix"),
        sa.UniqueConstraint("id", "deployment_id", name="uq_answer_key_deployment"),
    )
    op.create_index(
        "ix_answer_key_family", "answer_deployment_keys", ["deployment_id", "client_id"]
    )
    op.create_index(
        "ix_answer_key_validity",
        "answer_deployment_keys",
        ["deployment_id", "revoked_at", "expires_at"],
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM answer_deployment_keys")):
        raise RuntimeError("Deployment credential history cannot be dropped.")
    op.drop_table("answer_deployment_keys")
