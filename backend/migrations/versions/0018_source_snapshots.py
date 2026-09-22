"""Add immutable reusable Website source snapshots.

Revision ID: 0018
Revises: 0017
"""

import hashlib
import json
import uuid
from urllib.parse import urlsplit

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def _configuration(snapshot):
    execution = (snapshot or {}).get("execution") or {}
    return [
        {"id": node.get("id"), "config": node.get("config")}
        for node in execution.get("nodes", [])
        if node.get("type") == "source"
        and (node.get("config") or {}).get("kind") == "website"
    ]


def _config_hash(configuration):
    encoded = json.dumps(
        configuration, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _origin(value):
    parsed = urlsplit(value)
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _identity(configuration):
    origins = set()
    modes = set()
    for source in configuration:
        config = source["config"] or {}
        selection = config.get("selection") or {}
        modes.add(selection.get("mode", "unknown"))
        candidates = [
            selection.get("url"),
            selection.get("start_url"),
            selection.get("sitemap_url"),
            *(selection.get("urls") or []),
            *(config.get("allowed_origins") or []),
        ]
        origins.update(_origin(value) for value in candidates if value)
    return {"origins": sorted(origins), "selection_modes": sorted(modes)}


def _backfill(connection):
    rows = connection.execute(
        sa.text(
            """
            SELECT r.id AS run_id, r.project_id, r.snapshot, r.created_at,
                   r.finished_at, i.id AS index_id
              FROM ingestion_runs r
              JOIN index_versions i ON i.ingestion_run_id = r.id
             WHERE r.status = 'succeeded'
               AND r.snapshot->>'source_kind' = 'website'
             ORDER BY r.created_at, r.id
            """
        )
    ).mappings()
    numbers = {}
    snapshots_by_index = {}
    deferred = []
    for row in rows:
        run_snapshot = row["snapshot"] or {}
        if run_snapshot.get("reuse_stored"):
            deferred.append(row)
            continue
        members = list(
            connection.execute(
                sa.text(
                    """
                    SELECT m.source_node_id, m.source_item_id, m.source_revision_id,
                           s.canonical_location, r.provider_revision, r.size_bytes
                      FROM index_source_revisions m
                      JOIN source_items s ON s.id = m.source_item_id
                      JOIN source_revisions r ON r.id = m.source_revision_id
                     WHERE m.index_id = :index_id AND m.project_id = :project_id
                     ORDER BY m.source_node_id, s.canonical_location, m.source_revision_id
                    """
                ),
                {"index_id": row["index_id"], "project_id": row["project_id"]},
            ).mappings()
        )
        if not members:
            continue
        configuration = _configuration(run_snapshot)
        if not configuration:
            continue
        config_hash = _config_hash(configuration)
        key = (row["project_id"], config_hash)
        numbers[key] = numbers.get(key, 0) + 1
        snapshot_id = uuid.uuid4()
        counts = dict(
            connection.execute(
                sa.text(
                    """
                    SELECT outcome, count(*) AS count
                      FROM website_run_items
                     WHERE run_id = :run_id
                     GROUP BY outcome
                    """
                ),
                {"run_id": row["run_id"]},
            ).all()
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO source_snapshots (
                    id, project_id, source_kind, source_configuration,
                    source_config_hash, source_identity, connector_version,
                    snapshot_number, status, discovered_count, included_count,
                    excluded_count, duplicate_count, failed_count, new_count,
                    changed_count, unchanged_count, removed_count, total_bytes,
                    creating_ingestion_run_id, created_at, collected_at
                ) VALUES (
                    :id, :project_id, 'website', CAST(:configuration AS jsonb),
                    :config_hash, CAST(:identity AS jsonb), 'website-v1',
                    :number, 'ready', :discovered, :included, :excluded,
                    :duplicate, :failed, :new, :changed, :unchanged, :removed,
                    :total_bytes, :run_id, :created_at, :collected_at
                )
                """
            ),
            {
                "id": snapshot_id,
                "project_id": row["project_id"],
                "configuration": json.dumps(configuration),
                "config_hash": config_hash,
                "identity": json.dumps(_identity(configuration)),
                "number": numbers[key],
                "discovered": sum(counts.values()),
                "included": len(members),
                "excluded": counts.get("excluded", 0),
                "duplicate": counts.get("duplicate", 0),
                "failed": counts.get("failed", 0),
                "new": counts.get("new", 0),
                "changed": counts.get("changed", 0),
                "unchanged": counts.get("unchanged", 0),
                "removed": counts.get("removed", 0),
                "total_bytes": sum(member["size_bytes"] for member in members),
                "run_id": row["run_id"],
                "created_at": row["created_at"],
                "collected_at": row["finished_at"] or row["created_at"],
            },
        )
        for ordinal, member in enumerate(members):
            connection.execute(
                sa.text(
                    """
                    INSERT INTO source_snapshot_members (
                        snapshot_id, ordinal, project_id, source_node_id,
                        source_item_id, source_revision_id, inclusion_state, provenance
                    ) VALUES (
                        :snapshot_id, :ordinal, :project_id, :source_node_id,
                        :source_item_id, :source_revision_id, 'included',
                        CAST(:provenance AS jsonb)
                    )
                    """
                ),
                {
                    "snapshot_id": snapshot_id,
                    "ordinal": ordinal,
                    "project_id": row["project_id"],
                    "source_node_id": member["source_node_id"],
                    "source_item_id": member["source_item_id"],
                    "source_revision_id": member["source_revision_id"],
                    "provenance": json.dumps(
                        {
                            "canonical_location": member["canonical_location"],
                            "provider_revision": member["provider_revision"],
                        }
                    ),
                },
            )
        connection.execute(
            sa.text(
                "UPDATE ingestion_runs SET source_snapshot_id = :snapshot_id WHERE id = :run_id"
            ),
            {"snapshot_id": snapshot_id, "run_id": row["run_id"]},
        )
        connection.execute(
            sa.text(
                "UPDATE index_versions SET source_snapshot_id = :snapshot_id WHERE id = :index_id"
            ),
            {"snapshot_id": snapshot_id, "index_id": row["index_id"]},
        )
        snapshots_by_index[row["index_id"]] = snapshot_id

    for row in deferred:
        prior_index_id = (row["snapshot"] or {}).get("prior_ready_index_id")
        snapshot_id = (
            snapshots_by_index.get(uuid.UUID(prior_index_id))
            if prior_index_id
            else None
        )
        if snapshot_id is None:
            continue
        connection.execute(
            sa.text(
                "UPDATE ingestion_runs SET source_snapshot_id = :snapshot_id WHERE id = :run_id"
            ),
            {"snapshot_id": snapshot_id, "run_id": row["run_id"]},
        )
        connection.execute(
            sa.text(
                "UPDATE index_versions SET source_snapshot_id = :snapshot_id WHERE id = :index_id"
            ),
            {"snapshot_id": snapshot_id, "index_id": row["index_id"]},
        )
        snapshots_by_index[row["index_id"]] = snapshot_id


def upgrade():
    op.create_unique_constraint(
        "uq_source_revision_item_project",
        "source_revisions",
        ["id", "source_item_id", "project_id"],
    )
    op.create_table(
        "source_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("source_configuration", postgresql.JSONB(), nullable=False),
        sa.Column("source_config_hash", sa.String(64), nullable=False),
        sa.Column("source_identity", postgresql.JSONB(), nullable=False),
        sa.Column("connector_version", sa.String(80), nullable=False),
        sa.Column("snapshot_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="collecting"),
        sa.Column("discovered_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("included_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("excluded_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("changed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unchanged_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("removed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("creating_ingestion_run_id", sa.Uuid(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("collected_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["creating_ingestion_run_id", "project_id"],
            ["ingestion_runs.id", "ingestion_runs.project_id"],
            name="fk_source_snapshot_run_project",
        ),
        sa.UniqueConstraint("id", "project_id", name="uq_source_snapshot_project"),
        sa.UniqueConstraint(
            "creating_ingestion_run_id", name="uq_source_snapshot_creating_run"
        ),
        sa.UniqueConstraint(
            "project_id",
            "source_config_hash",
            "snapshot_number",
            name="uq_source_snapshot_number",
        ),
        sa.CheckConstraint("source_kind = 'website'", name="ck_source_snapshot_kind"),
        sa.CheckConstraint(
            "status IN ('collecting','ready','failed','cancelled')",
            name="ck_source_snapshot_status",
        ),
        sa.CheckConstraint(
            "char_length(source_config_hash) = 64",
            name="ck_source_snapshot_config_hash",
        ),
        sa.CheckConstraint("snapshot_number > 0", name="ck_source_snapshot_number"),
        sa.CheckConstraint(
            "discovered_count >= 0 AND included_count >= 0 AND excluded_count >= 0 "
            "AND duplicate_count >= 0 AND failed_count >= 0 AND new_count >= 0 "
            "AND changed_count >= 0 AND unchanged_count >= 0 AND removed_count >= 0 "
            "AND total_bytes >= 0",
            name="ck_source_snapshot_counts",
        ),
    )
    op.create_index(
        "ix_source_snapshots_project_source",
        "source_snapshots",
        ["project_id", "source_config_hash", "created_at", "id"],
    )
    op.create_table(
        "source_snapshot_members",
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_node_id", sa.String(80), nullable=False),
        sa.Column("source_item_id", sa.Uuid(), nullable=False),
        sa.Column("source_revision_id", sa.Uuid(), nullable=False),
        sa.Column(
            "inclusion_state", sa.String(16), nullable=False, server_default="included"
        ),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("snapshot_id", "ordinal"),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "project_id"],
            ["source_snapshots.id", "source_snapshots.project_id"],
            name="fk_source_snapshot_member_snapshot_project",
        ),
        sa.ForeignKeyConstraint(
            ["source_item_id", "project_id"],
            ["source_items.id", "source_items.project_id"],
            name="fk_source_snapshot_member_item_project",
        ),
        sa.ForeignKeyConstraint(
            ["source_revision_id", "source_item_id", "project_id"],
            [
                "source_revisions.id",
                "source_revisions.source_item_id",
                "source_revisions.project_id",
            ],
            name="fk_source_snapshot_member_revision_project",
        ),
        sa.UniqueConstraint(
            "snapshot_id", "source_item_id", name="uq_source_snapshot_member_item"
        ),
        sa.CheckConstraint("ordinal >= 0", name="ck_source_snapshot_member_ordinal"),
        sa.CheckConstraint(
            "inclusion_state = 'included'", name="ck_source_snapshot_member_inclusion"
        ),
    )
    op.create_index(
        "ix_source_snapshot_members_project",
        "source_snapshot_members",
        ["project_id", "snapshot_id", "ordinal"],
    )
    op.add_column("ingestion_runs", sa.Column("source_snapshot_id", sa.Uuid()))
    op.add_column("index_versions", sa.Column("source_snapshot_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_ingestion_run_source_snapshot_project",
        "ingestion_runs",
        "source_snapshots",
        ["source_snapshot_id", "project_id"],
        ["id", "project_id"],
    )
    op.create_foreign_key(
        "fk_index_source_snapshot_project",
        "index_versions",
        "source_snapshots",
        ["source_snapshot_id", "project_id"],
        ["id", "project_id"],
    )
    _backfill(op.get_bind())


def downgrade():
    op.drop_constraint(
        "fk_index_source_snapshot_project", "index_versions", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_ingestion_run_source_snapshot_project", "ingestion_runs", type_="foreignkey"
    )
    op.drop_column("index_versions", "source_snapshot_id")
    op.drop_column("ingestion_runs", "source_snapshot_id")
    op.drop_index(
        "ix_source_snapshot_members_project", table_name="source_snapshot_members"
    )
    op.drop_table("source_snapshot_members")
    op.drop_index("ix_source_snapshots_project_source", table_name="source_snapshots")
    op.drop_table("source_snapshots")
    op.drop_constraint(
        "uq_source_revision_item_project", "source_revisions", type_="unique"
    )
