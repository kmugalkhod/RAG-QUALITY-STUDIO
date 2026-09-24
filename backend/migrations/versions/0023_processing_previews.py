"""Add typed quality aggregates and bounded processing preview artifacts.

Revision ID: 0023
Revises: 0022
"""

import hashlib
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def _hash(value):
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def upgrade():
    op.drop_constraint("ck_source_snapshot_kind", "source_snapshots", type_="check")
    op.create_check_constraint(
        "ck_source_snapshot_kind",
        "source_snapshots",
        "source_kind IN ('website','s3','notion','confluence')",
    )
    op.drop_constraint("ck_source_preview_status", "source_previews", type_="check")
    op.add_column(
        "source_previews",
        sa.Column("pass_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "source_previews",
        sa.Column("warn_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "source_previews",
        sa.Column("exclude_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "source_previews",
        sa.Column(
            "quality_fail_count", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "source_previews",
        sa.Column(
            "known_compute_ms", sa.BigInteger(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "source_previews",
        sa.Column("configuration_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "source_previews",
        sa.Column(
            "fetch_mode",
            sa.String(length=24),
            nullable=False,
            server_default="network",
        ),
    )
    op.add_column(
        "source_previews",
        sa.Column(
            "cost_basis",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "source_previews",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, execution FROM source_previews")
    ).mappings()
    for row in rows:
        connection.execute(
            sa.text(
                "UPDATE source_previews SET configuration_hash = :hash, "
                "expires_at = created_at + interval '24 hours' WHERE id = :id"
            ),
            {"id": row["id"], "hash": _hash(row["execution"])},
        )
    op.alter_column("source_previews", "configuration_hash", nullable=False)
    op.alter_column("source_previews", "expires_at", nullable=False)
    op.create_check_constraint(
        "ck_source_preview_status",
        "source_previews",
        "status IN ('queued','running','succeeded','failed','cancelled','expired')",
    )
    op.create_check_constraint(
        "ck_source_preview_quality_counts",
        "source_previews",
        "pass_count >= 0 AND warn_count >= 0 AND exclude_count >= 0 "
        "AND quality_fail_count >= 0 AND pass_count + warn_count + exclude_count + "
        "quality_fail_count <= included_count",
    )
    op.create_check_constraint(
        "ck_source_preview_known_compute",
        "source_previews",
        "known_compute_ms >= 0",
    )

    op.add_column(
        "source_preview_items",
        sa.Column("quality_decision", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "source_preview_items",
        sa.Column(
            "processing_status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "source_preview_items",
        sa.Column(
            "fetch_mode",
            sa.String(length=24),
            nullable=False,
            server_default="network",
        ),
    )
    op.add_column(
        "source_preview_items",
        sa.Column("processing_config_hash", sa.String(length=64), nullable=True),
    )
    for name, default in (
        ("findings", "'[]'::jsonb"),
        ("metrics", "'{}'::jsonb"),
        ("stage_timings", "'{}'::jsonb"),
        ("cost_basis", "'{}'::jsonb"),
    ):
        op.add_column(
            "source_preview_items",
            sa.Column(
                name,
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text(default),
            ),
        )
    op.create_check_constraint(
        "ck_source_preview_item_quality",
        "source_preview_items",
        "quality_decision IS NULL OR quality_decision IN ('pass','warn','exclude','fail')",
    )
    op.create_check_constraint(
        "ck_source_preview_item_processing_status",
        "source_preview_items",
        "processing_status IN ('pending','succeeded','failed','skipped')",
    )

    op.create_table(
        "source_preview_representations",
        sa.Column("preview_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_ordinal", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=16), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("block_type", sa.String(length=40), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.CheckConstraint(
            "stage IN ('raw','extracted','cleaned','diff','chunks')",
            name="ck_source_preview_representation_stage",
        ),
        sa.CheckConstraint(
            "ordinal >= 0", name="ck_source_preview_representation_ordinal"
        ),
        sa.ForeignKeyConstraint(
            ["preview_id", "item_ordinal"],
            ["source_preview_items.preview_id", "source_preview_items.ordinal"],
            name="fk_source_preview_representation_item",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "preview_id", "item_ordinal", "stage", "ordinal"
        ),
    )
    op.create_index(
        "ix_source_preview_representations_stage",
        "source_preview_representations",
        ["preview_id", "item_ordinal", "stage", "ordinal"],
    )


def downgrade():
    op.drop_index(
        "ix_source_preview_representations_stage",
        table_name="source_preview_representations",
    )
    op.drop_table("source_preview_representations")
    op.drop_constraint(
        "ck_source_preview_item_processing_status",
        "source_preview_items",
        type_="check",
    )
    op.drop_constraint(
        "ck_source_preview_item_quality", "source_preview_items", type_="check"
    )
    for name in (
        "cost_basis",
        "stage_timings",
        "metrics",
        "findings",
        "processing_config_hash",
        "fetch_mode",
        "processing_status",
        "quality_decision",
    ):
        op.drop_column("source_preview_items", name)
    op.drop_constraint(
        "ck_source_preview_known_compute", "source_previews", type_="check"
    )
    op.drop_constraint(
        "ck_source_preview_quality_counts", "source_previews", type_="check"
    )
    op.drop_constraint("ck_source_preview_status", "source_previews", type_="check")
    op.create_check_constraint(
        "ck_source_preview_status",
        "source_previews",
        "status IN ('queued','running','succeeded','failed','cancelled')",
    )
    for name in (
        "expires_at",
        "cost_basis",
        "fetch_mode",
        "configuration_hash",
        "known_compute_ms",
        "quality_fail_count",
        "exclude_count",
        "warn_count",
        "pass_count",
    ):
        op.drop_column("source_previews", name)
    op.drop_constraint("ck_source_snapshot_kind", "source_snapshots", type_="check")
    op.create_check_constraint(
        "ck_source_snapshot_kind", "source_snapshots", "source_kind = 'website'"
    )
