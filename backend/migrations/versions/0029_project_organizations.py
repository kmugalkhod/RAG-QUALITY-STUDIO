"""Scope projects to Clerk organizations without guessing legacy ownership."""

import os

from alembic import op
import sqlalchemy as sa

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "projects", sa.Column("organization_id", sa.String(100), nullable=True)
    )
    connection = op.get_bind()
    legacy_count = connection.scalar(sa.text("SELECT count(*) FROM projects"))
    if legacy_count:
        organization_id = os.environ.get("LEGACY_PROJECT_ORG_ID", "")
        if not organization_id.startswith("org_") or len(organization_id) > 100:
            raise RuntimeError(
                "Existing projects require an explicit LEGACY_PROJECT_ORG_ID before migration."
            )
        connection.execute(
            sa.text("UPDATE projects SET organization_id = :organization_id"),
            {"organization_id": organization_id},
        )
    op.create_index(
        "ix_projects_org_created", "projects", ["organization_id", "created_at", "id"]
    )


def downgrade():
    op.drop_index("ix_projects_org_created", table_name="projects")
    op.drop_column("projects", "organization_id")
