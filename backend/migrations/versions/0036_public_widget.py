"""Opt-in public visitor access for the website widget."""

from alembic import op
import sqlalchemy as sa

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "answer_deployments",
        sa.Column(
            "widget_public_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "answer_deployment_keys",
        sa.Column("kind", sa.String(20), nullable=False, server_default="server"),
    )
    op.create_check_constraint(
        "ck_answer_key_kind",
        "answer_deployment_keys",
        "kind IN ('server','public_widget')",
    )
    op.create_index(
        "uq_public_widget_key",
        "answer_deployment_keys",
        ["deployment_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'public_widget'"),
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM answer_deployment_keys WHERE kind = 'public_widget')"
        )
    ):
        raise RuntimeError("Public widget keys are retained.")
    op.drop_index("uq_public_widget_key", table_name="answer_deployment_keys")
    op.drop_constraint("ck_answer_key_kind", "answer_deployment_keys", type_="check")
    op.drop_column("answer_deployment_keys", "kind")
    op.drop_column("answer_deployments", "widget_public_enabled")
