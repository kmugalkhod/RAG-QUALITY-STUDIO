"""Durable management command replay receipts without stored key secrets."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "deployment_command_receipts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("principal_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("deployment_id", sa.Uuid()),
        sa.Column("command_kind", sa.String(40), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("response", JSONB(), nullable=False),
        sa.Column(
            "secret_issued", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "principal_id", "command_kind", "key_hash", name="uq_deployment_command_key"
        ),
    )
    op.create_index(
        "ix_deployment_command_expiry", "deployment_command_receipts", ["expires_at"]
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM deployment_command_receipts)")
    ):
        raise RuntimeError("Command receipts are retained while replay history exists.")
    op.drop_index(
        "ix_deployment_command_expiry", table_name="deployment_command_receipts"
    )
    op.drop_table("deployment_command_receipts")
