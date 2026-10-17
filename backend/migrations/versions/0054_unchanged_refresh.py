"""Unchanged refreshes publish no new index version.

Spec 0012 D8. A run whose passages and embedding settings equal the knowledge
set's current ready version publishes nothing and records that version in
`unchanged_index_id`. Such a run succeeds with `published_count = 0`, so the
completion check accepts either one published version or a recorded unchanged
one. Existing runs are unaffected.

Earlier schemas cannot record a succeeded run that published nothing, so a
downgrade keeps such runs as cancelled, with an error that says why, instead
of deleting them.
"""

import sqlalchemy as sa
from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None

OLD_COMPLETE = (
    "status != 'succeeded' OR "
    "(stage = 'complete' AND progress = 100 AND published_count = 1 "
    "AND processed_count + failed_count = discovered_count "
    "AND embedded_count = chunk_count)"
)
NEW_COMPLETE = (
    "status != 'succeeded' OR "
    "(stage = 'complete' AND progress = 100 "
    "AND (published_count = 1 OR "
    "(published_count = 0 AND unchanged_index_id IS NOT NULL)) "
    "AND processed_count + failed_count = discovered_count "
    "AND embedded_count = chunk_count)"
)


def upgrade():
    op.add_column(
        "ingestion_runs", sa.Column("unchanged_index_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_ingestion_run_unchanged_index_project",
        "ingestion_runs",
        "index_versions",
        ["unchanged_index_id", "project_id"],
        ["id", "project_id"],
    )
    op.drop_constraint("ck_ingestion_run_complete", "ingestion_runs", type_="check")
    op.create_check_constraint(
        "ck_ingestion_run_complete", "ingestion_runs", NEW_COMPLETE
    )


def downgrade():
    op.drop_constraint("ck_ingestion_run_complete", "ingestion_runs", type_="check")
    op.execute(
        "UPDATE ingestion_runs SET status = 'cancelled', "
        "error = 'Published nothing: no changes since the current version.' "
        "WHERE unchanged_index_id IS NOT NULL"
    )
    op.create_check_constraint(
        "ck_ingestion_run_complete", "ingestion_runs", OLD_COMPLETE
    )
    op.drop_constraint(
        "fk_ingestion_run_unchanged_index_project", "ingestion_runs", type_="foreignkey"
    )
    op.drop_column("ingestion_runs", "unchanged_index_id")
