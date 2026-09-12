"""Add encrypted project source connections."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("secret_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("secret_nonce", sa.LargeBinary(12), nullable=False),
        sa.Column("key_version", sa.String(32), nullable=False),
        sa.Column("secret_schema_version", sa.Integer(), nullable=False),
        sa.Column("redacted_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("id", "project_id", name="uq_source_connection_project"),
        sa.UniqueConstraint(
            "project_id", "name", name="uq_source_connection_project_name"
        ),
        sa.CheckConstraint(
            "kind IN ('s3','notion','confluence')",
            name="ck_source_connection_kind",
        ),
        sa.CheckConstraint(
            "status IN ('untested','valid','invalid','unavailable')",
            name="ck_source_connection_status",
        ),
        sa.CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 120",
            name="ck_source_connection_name",
        ),
        sa.CheckConstraint(
            "octet_length(secret_nonce) = 12",
            name="ck_source_connection_nonce",
        ),
        sa.CheckConstraint(
            "octet_length(secret_ciphertext) >= 16",
            name="ck_source_connection_ciphertext",
        ),
        sa.CheckConstraint(
            "secret_schema_version = 1",
            name="ck_source_connection_secret_schema",
        ),
    )
    op.create_index(
        "ix_source_connections_project_created",
        "source_connections",
        ["project_id", "created_at", "id"],
    )
    op.create_table(
        "source_connection_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("actor", sa.String(32), nullable=False),
        sa.Column("safe_metadata", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["connection_id", "project_id"],
            ["source_connections.id", "source_connections.project_id"],
            name="fk_source_connection_event_connection_project",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "event_type IN ('created','credentials_rotated','rewrapped','tested')",
            name="ck_source_connection_event_type",
        ),
        sa.CheckConstraint(
            "outcome IN ('succeeded','failed','unavailable')",
            name="ck_source_connection_event_outcome",
        ),
    )
    op.create_index(
        "ix_source_connection_events_connection_created",
        "source_connection_events",
        ["connection_id", "created_at", "id"],
    )


def downgrade():
    op.drop_index(
        "ix_source_connection_events_connection_created",
        table_name="source_connection_events",
    )
    op.drop_table("source_connection_events")
    op.drop_index(
        "ix_source_connections_project_created", table_name="source_connections"
    )
    op.drop_table("source_connections")
