"""Private website widget configuration and visitor-scoped tokens."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "answer_deployments",
        sa.Column(
            "widget_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "answer_deployments",
        sa.Column("widget_origins", JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "answer_deployments",
        sa.Column("widget_branding", JSONB(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "deployed_answer_runs",
        sa.Column(
            "caller_kind", sa.String(16), nullable=False, server_default="server_key"
        ),
    )
    op.add_column(
        "deployed_answer_runs", sa.Column("widget_visitor_binding", sa.String(64))
    )
    op.create_check_constraint(
        "ck_deployed_run_caller_kind",
        "deployed_answer_runs",
        "caller_kind IN ('server_key','widget')",
    )
    op.create_table(
        "widget_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("deployment_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.String(100), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("key_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("visitor_binding", sa.String(64), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("site_origin", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["deployment_id", "organization_id", "project_id"],
            [
                "answer_deployments.id",
                "answer_deployments.organization_id",
                "answer_deployments.project_id",
            ],
            name="fk_widget_token_deployment_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["key_id", "deployment_id"],
            ["answer_deployment_keys.id", "answer_deployment_keys.deployment_id"],
            name="fk_widget_token_key",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("token_hash", name="uq_widget_token_hash"),
    )
    op.create_index("ix_widget_token_expiry", "widget_tokens", ["expires_at"])
    op.create_index(
        "ix_widget_token_visitor",
        "widget_tokens",
        ["deployment_id", "visitor_binding", "created_at"],
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM widget_tokens)")
    ) or op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM deployed_answer_runs WHERE caller_kind = 'widget')"
        )
    ):
        raise RuntimeError("Widget tokens or runs are retained.")
    op.drop_index("ix_widget_token_visitor", table_name="widget_tokens")
    op.drop_index("ix_widget_token_expiry", table_name="widget_tokens")
    op.drop_table("widget_tokens")
    op.drop_constraint(
        "ck_deployed_run_caller_kind", "deployed_answer_runs", type_="check"
    )
    op.drop_column("deployed_answer_runs", "widget_visitor_binding")
    op.drop_column("deployed_answer_runs", "caller_kind")
    for column in ("widget_branding", "widget_origins", "widget_enabled"):
        op.drop_column("answer_deployments", column)
