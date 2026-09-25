"""Add sensitive findings and encrypted raw-artifact envelopes.

Revision ID: 0025
Revises: 0024
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "documents",
        "media_type",
        existing_type=sa.String(length=32),
        type_=sa.String(length=100),
        existing_nullable=False,
    )
    op.create_table(
        "user_identities",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("external_subject", sa.String(length=500), nullable=False),
        sa.Column("email", sa.String(length=320)),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_subject", name="uq_user_identity_subject"),
    )
    op.create_index("ix_user_identity_updated", "user_identities", ["updated_at", "id"])
    op.create_table(
        "project_memberships",
        sa.Column("project_id", postgresql.UUID(), nullable=False),
        sa.Column("user_id", postgresql.UUID(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "role IN ('owner','admin','editor','viewer')",
            name="ck_project_membership_role",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_membership_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_identities.id"],
            name="fk_project_membership_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("project_id", "user_id"),
    )
    op.create_index(
        "ix_project_membership_user",
        "project_memberships",
        ["user_id", "project_id"],
    )
    op.create_table(
        "sensitive_access_events",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("project_id", postgresql.UUID(), nullable=False),
        sa.Column("user_id", postgresql.UUID(), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("resource_kind", sa.String(length=40), nullable=False),
        sa.Column("resource_id", postgresql.UUID()),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "action IN ('raw_artifact_read','full_diff_read',"
            "'sensitive_findings_read','thumbnail_read','preview_protected_read',"
            "'artifact_key_rewrap')",
            name="ck_sensitive_access_action",
        ),
        sa.CheckConstraint(
            "outcome IN ('granted','denied')",
            name="ck_sensitive_access_outcome",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user_identities.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sensitive_access_project_time",
        "sensitive_access_events",
        ["project_id", "created_at", "id"],
    )
    op.add_column(
        "documents",
        sa.Column(
            "artifact_state",
            sa.String(length=24),
            nullable=False,
            server_default="legacy_plaintext",
        ),
    )
    op.add_column("documents", sa.Column("artifact_encryption_schema", sa.Integer()))
    op.add_column("documents", sa.Column("artifact_key_version", sa.String(length=32)))
    op.add_column("documents", sa.Column("artifact_wrapped_key", sa.LargeBinary()))
    op.add_column("documents", sa.Column("artifact_wrap_nonce", sa.LargeBinary()))
    op.add_column("documents", sa.Column("artifact_content_nonce", sa.LargeBinary()))
    op.add_column(
        "documents", sa.Column("raw_retained_until", sa.DateTime(timezone=True))
    )
    op.add_column("documents", sa.Column("raw_deleted_at", sa.DateTime(timezone=True)))
    op.add_column("documents", sa.Column("raw_deletion_token", postgresql.UUID()))
    op.add_column(
        "documents", sa.Column("raw_deletion_claimed_at", sa.DateTime(timezone=True))
    )
    op.create_check_constraint(
        "ck_document_artifact_state",
        "documents",
        "artifact_state IN ('legacy_plaintext','encrypted','deleting','deleted')",
    )
    op.create_check_constraint(
        "ck_document_artifact_envelope",
        "documents",
        "(artifact_state = 'legacy_plaintext' AND artifact_encryption_schema IS NULL "
        "AND artifact_key_version IS NULL AND artifact_wrapped_key IS NULL "
        "AND artifact_wrap_nonce IS NULL AND artifact_content_nonce IS NULL) OR "
        "(artifact_state IN ('encrypted','deleting') "
        "AND artifact_encryption_schema = 1 "
        "AND artifact_key_version IS NOT NULL AND artifact_wrapped_key IS NOT NULL "
        "AND artifact_wrap_nonce IS NOT NULL AND artifact_content_nonce IS NOT NULL) OR "
        "(artifact_state = 'deleted' AND artifact_encryption_schema IS NULL "
        "AND artifact_key_version IS NULL AND artifact_wrapped_key IS NULL "
        "AND artifact_wrap_nonce IS NULL AND artifact_content_nonce IS NULL)",
    )
    op.create_index(
        "ix_documents_raw_retention",
        "documents",
        ["artifact_state", "raw_retained_until"],
    )
    op.add_column(
        "content_derivations",
        sa.Column(
            "sensitive_findings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "content_derivations",
        sa.Column(
            "sensitive_data_applied",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "content_derivations",
        sa.Column(
            "protected_text",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "content_blocks", sa.Column("protected_text_ciphertext", sa.LargeBinary())
    )
    op.add_column("content_blocks", sa.Column("protected_text_nonce", sa.LargeBinary()))
    op.add_column(
        "source_previews",
        sa.Column(
            "protected_content",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("source_previews", sa.Column("protected_schema", sa.Integer()))
    op.add_column(
        "source_previews", sa.Column("protected_key_version", sa.String(length=32))
    )
    op.add_column(
        "source_previews", sa.Column("protected_wrapped_key", sa.LargeBinary())
    )
    op.add_column(
        "source_previews", sa.Column("protected_wrap_nonce", sa.LargeBinary())
    )
    op.create_check_constraint(
        "ck_source_preview_protected_envelope",
        "source_previews",
        "(protected_content = false AND protected_schema IS NULL "
        "AND protected_key_version IS NULL AND protected_wrapped_key IS NULL "
        "AND protected_wrap_nonce IS NULL) OR "
        "(protected_content = true AND protected_schema = 1 "
        "AND protected_key_version IS NOT NULL AND protected_wrapped_key IS NOT NULL "
        "AND protected_wrap_nonce IS NOT NULL)",
    )
    op.add_column(
        "source_preview_representations",
        sa.Column("protected_payload", sa.LargeBinary()),
    )
    op.add_column(
        "source_preview_representations",
        sa.Column("protected_nonce", sa.LargeBinary()),
    )


def downgrade():
    op.drop_column("source_preview_representations", "protected_nonce")
    op.drop_column("source_preview_representations", "protected_payload")
    op.drop_constraint(
        "ck_source_preview_protected_envelope", "source_previews", type_="check"
    )
    for column in (
        "protected_wrap_nonce",
        "protected_wrapped_key",
        "protected_key_version",
        "protected_schema",
        "protected_content",
    ):
        op.drop_column("source_previews", column)
    op.drop_column("content_blocks", "protected_text_nonce")
    op.drop_column("content_blocks", "protected_text_ciphertext")
    op.drop_column("content_derivations", "protected_text")
    op.drop_column("content_derivations", "sensitive_data_applied")
    op.drop_column("content_derivations", "sensitive_findings")
    op.drop_index("ix_documents_raw_retention", table_name="documents")
    op.drop_constraint("ck_document_artifact_envelope", "documents", type_="check")
    op.drop_constraint("ck_document_artifact_state", "documents", type_="check")
    for column in (
        "raw_deletion_claimed_at",
        "raw_deletion_token",
        "raw_deleted_at",
        "raw_retained_until",
        "artifact_content_nonce",
        "artifact_wrap_nonce",
        "artifact_wrapped_key",
        "artifact_key_version",
        "artifact_encryption_schema",
        "artifact_state",
    ):
        op.drop_column("documents", column)
    op.drop_index(
        "ix_sensitive_access_project_time", table_name="sensitive_access_events"
    )
    op.drop_table("sensitive_access_events")
    op.drop_index("ix_project_membership_user", table_name="project_memberships")
    op.drop_table("project_memberships")
    op.drop_index("ix_user_identity_updated", table_name="user_identities")
    op.drop_table("user_identities")
    op.alter_column(
        "documents",
        "media_type",
        existing_type=sa.String(length=100),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
