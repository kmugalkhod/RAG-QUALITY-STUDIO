"""Add reusable derivations and structure-aware chunk metadata.

Revision ID: 0022
Revises: 0021
"""

import hashlib
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def _derivation_hash(configuration):
    if not isinstance(configuration, dict) or configuration.get("schema_version") != 2:
        return None
    versions = configuration.get("versions") or {}
    value = {
        "schema_version": 2,
        "versions": {
            "extractor": versions.get("extractor"),
            "cleaner": versions.get("cleaner"),
        },
        "extract": configuration.get("extract") or {},
        "clean": configuration.get("clean") or {},
    }
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def upgrade():
    op.drop_constraint(
        "uq_source_revision_document", "source_revisions", type_="unique"
    )
    op.drop_constraint(
        "source_revisions_artifact_storage_name_key",
        "source_revisions",
        type_="unique",
    )
    op.add_column(
        "processing_runs",
        sa.Column("derivation_config_hash", sa.String(length=64)),
    )
    op.add_column(
        "processing_runs",
        sa.Column("reused_from_processing_run_id", sa.Uuid()),
    )
    op.create_foreign_key(
        "fk_processing_run_reused_from",
        "processing_runs",
        "processing_runs",
        ["reused_from_processing_run_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_processing_run_derivation_hash",
        "processing_runs",
        "derivation_config_hash IS NULL OR length(derivation_config_hash) = 64",
    )
    op.create_index(
        "ix_runs_derivation_config",
        "processing_runs",
        ["document_id", "derivation_config_hash"],
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, processing_config FROM processing_runs")
    ).mappings()
    for row in rows:
        value = _derivation_hash(row["processing_config"])
        if value:
            connection.execute(
                sa.text(
                    "UPDATE processing_runs SET derivation_config_hash=:value WHERE id=:id"
                ),
                {"id": row["id"], "value": value},
            )

    op.add_column("chunks", sa.Column("embedding_text", sa.Text()))
    op.add_column("chunks", sa.Column("token_count", sa.Integer()))
    op.add_column("chunks", sa.Column("embedding_token_count", sa.Integer()))
    op.add_column(
        "chunks",
        sa.Column(
            "chunk_role",
            sa.String(length=16),
            nullable=False,
            server_default="leaf",
        ),
    )
    op.add_column("chunks", sa.Column("parent_ordinal", sa.Integer()))
    op.add_column(
        "chunks",
        sa.Column(
            "findings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_check_constraint(
        "ck_chunk_role", "chunks", "chunk_role IN ('leaf','parent','child')"
    )
    op.create_check_constraint(
        "ck_chunk_parent_role",
        "chunks",
        "(chunk_role = 'child' AND parent_ordinal IS NOT NULL) OR "
        "(chunk_role <> 'child' AND parent_ordinal IS NULL)",
    )
    op.create_check_constraint(
        "ck_chunk_token_count", "chunks", "token_count IS NULL OR token_count > 0"
    )
    op.create_check_constraint(
        "ck_chunk_embedding_token_count",
        "chunks",
        "embedding_token_count IS NULL OR embedding_token_count > 0",
    )
    op.create_foreign_key(
        "fk_chunk_parent",
        "chunks",
        "chunks",
        ["run_id", "parent_ordinal"],
        ["run_id", "ordinal"],
    )
    op.create_index("ix_chunks_parent", "chunks", ["run_id", "parent_ordinal"])

    op.create_unique_constraint(
        "uq_content_derivation_id_kind", "content_derivations", ["id", "kind"]
    )
    op.create_unique_constraint(
        "uq_content_derivation_document_project",
        "content_derivations",
        ["id", "document_id", "project_id"],
    )
    op.create_table(
        "processing_derivations",
        sa.Column("processing_run_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("derivation_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("reused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "kind IN ('extracted','cleaned')", name="ck_processing_derivation_kind"
        ),
        sa.ForeignKeyConstraint(
            ["processing_run_id", "document_id"],
            ["processing_runs.id", "processing_runs.document_id"],
            name="fk_processing_derivation_run_document",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "project_id"],
            ["documents.id", "documents.project_id"],
            name="fk_processing_derivation_document_project",
        ),
        sa.ForeignKeyConstraint(
            ["derivation_id", "document_id", "project_id"],
            [
                "content_derivations.id",
                "content_derivations.document_id",
                "content_derivations.project_id",
            ],
            name="fk_processing_derivation_content",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("processing_run_id", "kind"),
        sa.UniqueConstraint(
            "processing_run_id",
            "kind",
            "derivation_id",
            name="uq_processing_derivation_reference",
        ),
    )
    connection.execute(
        sa.text(
            "INSERT INTO processing_derivations "
            "(processing_run_id, kind, derivation_id, document_id, project_id, reused) "
            "SELECT processing_run_id, kind, id, document_id, project_id, false "
            "FROM content_derivations"
        )
    )
    op.drop_constraint(
        "fk_chunk_block_span_derivation_run",
        "chunk_block_spans",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_chunk_span_processing_derivation",
        "chunk_block_spans",
        "processing_derivations",
        ["run_id", "derivation_kind", "derivation_id"],
        ["processing_run_id", "kind", "derivation_id"],
        ondelete="CASCADE",
    )


def downgrade():
    connection = op.get_bind()
    incompatible = connection.execute(
        sa.text(
            "SELECT 1 FROM processing_derivations pd "
            "JOIN content_derivations cd ON cd.id = pd.derivation_id "
            "WHERE pd.processing_run_id <> cd.processing_run_id LIMIT 1"
        )
    ).first()
    structured = connection.execute(
        sa.text(
            "SELECT 1 FROM chunks WHERE chunk_role <> 'leaf' "
            "OR embedding_text IS NOT NULL OR token_count IS NOT NULL LIMIT 1"
        )
    ).first()
    if incompatible or structured:
        raise RuntimeError(
            "Downgrade refused while reusable or structure-aware chunk history exists."
        )

    duplicate_artifacts = connection.execute(
        sa.text(
            "SELECT 1 FROM source_revisions GROUP BY artifact_storage_name "
            "HAVING count(*) > 1 LIMIT 1"
        )
    ).first()
    duplicate_documents = connection.execute(
        sa.text(
            "SELECT 1 FROM source_revisions GROUP BY document_id "
            "HAVING count(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate_artifacts or duplicate_documents:
        raise RuntimeError(
            "Downgrade refused while source revisions share reusable raw artifacts."
        )

    op.drop_constraint(
        "fk_chunk_span_processing_derivation",
        "chunk_block_spans",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_chunk_block_span_derivation_run",
        "chunk_block_spans",
        "content_derivations",
        ["derivation_id", "run_id", "derivation_kind"],
        ["id", "processing_run_id", "kind"],
        ondelete="CASCADE",
    )
    op.drop_table("processing_derivations")
    op.drop_constraint(
        "uq_content_derivation_document_project",
        "content_derivations",
        type_="unique",
    )
    op.drop_constraint(
        "uq_content_derivation_id_kind", "content_derivations", type_="unique"
    )

    op.drop_index("ix_chunks_parent", table_name="chunks")
    op.drop_constraint("fk_chunk_parent", "chunks", type_="foreignkey")
    op.drop_constraint("ck_chunk_embedding_token_count", "chunks", type_="check")
    op.drop_constraint("ck_chunk_token_count", "chunks", type_="check")
    op.drop_constraint("ck_chunk_parent_role", "chunks", type_="check")
    op.drop_constraint("ck_chunk_role", "chunks", type_="check")
    op.drop_column("chunks", "findings")
    op.drop_column("chunks", "parent_ordinal")
    op.drop_column("chunks", "chunk_role")
    op.drop_column("chunks", "embedding_token_count")
    op.drop_column("chunks", "token_count")
    op.drop_column("chunks", "embedding_text")

    op.drop_index("ix_runs_derivation_config", table_name="processing_runs")
    op.drop_constraint(
        "ck_processing_run_derivation_hash", "processing_runs", type_="check"
    )
    op.drop_constraint(
        "fk_processing_run_reused_from", "processing_runs", type_="foreignkey"
    )
    op.drop_column("processing_runs", "reused_from_processing_run_id")
    op.drop_column("processing_runs", "derivation_config_hash")
    op.create_unique_constraint(
        "source_revisions_artifact_storage_name_key",
        "source_revisions",
        ["artifact_storage_name"],
    )
    op.create_unique_constraint(
        "uq_source_revision_document", "source_revisions", ["document_id"]
    )
