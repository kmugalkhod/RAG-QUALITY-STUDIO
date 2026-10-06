"""Widen processing_runs.parser_version to the extractor-version contract length.

The layout-ocr-v2 extractor version (65 characters) exceeded varchar(64), so v2
ingestion runs could not create their processing runs. ExtractedDocumentV1 and
content_derivations.engine_version already allow 120 characters.
"""

from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE processing_runs ALTER COLUMN parser_version TYPE varchar(120)"
    )


def downgrade():
    # Fails instead of truncating when a stored version is longer than 64 characters.
    op.execute(
        "ALTER TABLE processing_runs ALTER COLUMN parser_version TYPE varchar(64)"
    )
