"""Reuse an extracted document across cleaning changes.

Spec 0012 C5. `extraction_config_hash` identifies the extraction settings and
extractor version alone, so a run whose only change is cleaning reuses the
extracted document of an earlier run of the same file instead of extracting it
again (OCR included). Existing schema-v2 runs are backfilled from their saved
processing config with the same canonical JSON hash the application computes,
so they can be reused immediately. Downgrade drops both columns; no processing
result changes.
"""

import hashlib
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def _extraction_hash(config: dict) -> str | None:
    versions = config.get("versions") or {}
    extractor = versions.get("extractor")
    if config.get("schema_version") != 2 or not isinstance(extractor, str):
        return None
    value = {
        "schema_version": 2,
        "versions": {"extractor": extractor},
        "extract": config.get("extract") or {},
    }
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def upgrade():
    op.add_column(
        "processing_runs",
        sa.Column("extraction_config_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "processing_runs",
        sa.Column(
            "reused_extraction_from_processing_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "processing_runs.id",
                name="fk_processing_run_reused_extraction",
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_runs_extraction_config",
        "processing_runs",
        ["document_id", "extraction_config_hash"],
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, processing_config FROM processing_runs "
            "WHERE processing_config IS NOT NULL"
        )
    ).all()
    updates = [
        {"id": row.id, "hash": value}
        for row in rows
        if (value := _extraction_hash(row.processing_config or {})) is not None
    ]
    for start in range(0, len(updates), 500):
        connection.execute(
            sa.text(
                "UPDATE processing_runs SET extraction_config_hash = :hash "
                "WHERE id = :id"
            ),
            updates[start : start + 500],
        )


def downgrade():
    op.drop_index("ix_runs_extraction_config", table_name="processing_runs")
    op.drop_column("processing_runs", "reused_extraction_from_processing_run_id")
    op.drop_column("processing_runs", "extraction_config_hash")
