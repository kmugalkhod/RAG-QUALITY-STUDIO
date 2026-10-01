"""Organization-approved OpenRouter chat models."""

from alembic import op
import sqlalchemy as sa

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_model_approvals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("scope_key", sa.String(120), nullable=False),
        sa.Column("organization_id", sa.String(100)),
        sa.Column(
            "provider", sa.String(32), nullable=False, server_default="openrouter"
        ),
        sa.Column("model_id", sa.String(200), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("context_length", sa.Integer(), nullable=False),
        sa.Column("prompt_usd_per_mtok", sa.Numeric(18, 6)),
        sa.Column("completion_usd_per_mtok", sa.Numeric(18, 6)),
        sa.Column("catalog_fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("approved_by", sa.String(500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "scope_key", "provider", "model_id", name="uq_chat_model_approval"
        ),
        sa.CheckConstraint("provider IN ('openrouter')", name="ck_chat_model_provider"),
        sa.CheckConstraint(
            "scope_key = 'instance' OR scope_key = 'organization:' || organization_id",
            name="ck_chat_model_scope",
        ),
        sa.CheckConstraint("context_length >= 2048", name="ck_chat_model_context"),
    )
    op.create_index(
        "uq_chat_model_default",
        "chat_model_approvals",
        ["scope_key", "provider"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )


def downgrade():
    op.drop_index("uq_chat_model_default", table_name="chat_model_approvals")
    op.drop_table("chat_model_approvals")
