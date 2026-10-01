"""Encrypted organization OpenRouter keys and their audit events."""

from alembic import op
import sqlalchemy as sa

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "provider_credentials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("scope_key", sa.String(120), nullable=False),
        sa.Column("organization_id", sa.String(100)),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(12), nullable=False),
        sa.Column("wrapped_key", sa.LargeBinary(), nullable=False),
        sa.Column("wrap_nonce", sa.LargeBinary(), nullable=False),
        sa.Column("key_version", sa.String(32), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("redacted_hint", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_by", sa.String(500), nullable=False),
        sa.Column("updated_by", sa.String(500), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True)),
        sa.Column("rotated_at", sa.DateTime(timezone=True)),
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
            "scope_key", "provider", name="uq_provider_credential_scope"
        ),
        sa.CheckConstraint(
            "provider IN ('openrouter')", name="ck_provider_credential_kind"
        ),
        sa.CheckConstraint(
            "status IN ('active','rejected')", name="ck_provider_credential_status"
        ),
        sa.CheckConstraint(
            "scope_key = 'instance' OR scope_key = 'organization:' || organization_id",
            name="ck_provider_credential_scope",
        ),
        sa.CheckConstraint(
            "octet_length(nonce) = 12", name="ck_provider_credential_nonce"
        ),
        sa.CheckConstraint(
            "octet_length(ciphertext) >= 16", name="ck_provider_credential_ciphertext"
        ),
        sa.CheckConstraint("schema_version = 1", name="ck_provider_credential_schema"),
    )
    op.create_table(
        "provider_credential_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("scope_key", sa.String(120), nullable=False),
        sa.Column("credential_id", sa.Uuid()),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("actor", sa.String(500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "event_type IN ('created','rotated','deleted','tested','rejected_by_provider')",
            name="ck_provider_credential_event_type",
        ),
        sa.CheckConstraint(
            "outcome IN ('succeeded','failed')",
            name="ck_provider_credential_event_outcome",
        ),
    )
    op.create_index(
        "ix_provider_credential_events_scope_created",
        "provider_credential_events",
        ["scope_key", "created_at", "id"],
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM provider_credentials)")
    ):
        raise RuntimeError("Stored provider credentials are retained.")
    op.drop_index(
        "ix_provider_credential_events_scope_created",
        table_name="provider_credential_events",
    )
    op.drop_table("provider_credential_events")
    op.drop_table("provider_credentials")
