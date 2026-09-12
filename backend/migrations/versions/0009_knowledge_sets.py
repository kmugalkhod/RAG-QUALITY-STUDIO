"""Add knowledge sets and scope immutable indexes to explicit destinations."""

from alembic import op
import sqlalchemy as sa


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_sets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("id", "project_id", name="uq_knowledge_set_project"),
        sa.UniqueConstraint("project_id", "name", name="uq_knowledge_set_name"),
        sa.CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 120",
            name="ck_knowledge_set_name",
        ),
    )
    op.create_index(
        "ix_knowledge_sets_project_created",
        "knowledge_sets",
        ["project_id", "created_at", "id"],
    )
    op.execute(
        """
        INSERT INTO knowledge_sets (id, project_id, name)
        SELECT gen_random_uuid(), id, 'Uploaded documents'
        FROM projects
        """
    )

    op.add_column(
        "index_versions", sa.Column("knowledge_set_id", sa.Uuid(), nullable=True)
    )
    op.execute(
        """
        UPDATE index_versions AS indexes
        SET knowledge_set_id = sets.id
        FROM knowledge_sets AS sets
        WHERE sets.project_id = indexes.project_id
          AND sets.name = 'Uploaded documents'
        """
    )
    op.alter_column("index_versions", "knowledge_set_id", nullable=False)
    op.drop_index("uq_index_active_project", table_name="index_versions")
    op.drop_constraint("uq_index_version", "index_versions", type_="unique")
    op.create_foreign_key(
        "fk_index_knowledge_set_project",
        "index_versions",
        "knowledge_sets",
        ["knowledge_set_id", "project_id"],
        ["id", "project_id"],
    )
    op.create_unique_constraint(
        "uq_index_knowledge_set_version",
        "index_versions",
        ["knowledge_set_id", "version"],
    )
    op.create_index(
        "ix_indexes_knowledge_set_created",
        "index_versions",
        ["knowledge_set_id", "created_at", "id"],
    )
    op.create_index(
        "uq_index_active_knowledge_set",
        "index_versions",
        ["knowledge_set_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued','running')"),
    )

    op.add_column(
        "knowledge_sets", sa.Column("current_ready_index_id", sa.Uuid(), nullable=True)
    )
    op.execute(
        """
        ALTER TABLE knowledge_sets
        ADD CONSTRAINT fk_knowledge_set_current_index_project
        FOREIGN KEY (current_ready_index_id, project_id)
        REFERENCES index_versions (id, project_id)
        ON DELETE SET NULL (current_ready_index_id)
        """
    )
    op.execute(
        """
        UPDATE knowledge_sets AS sets
        SET current_ready_index_id = (
            SELECT indexes.id
            FROM index_versions AS indexes
            WHERE indexes.knowledge_set_id = sets.id
              AND indexes.status = 'succeeded'
            ORDER BY indexes.version DESC
            LIMIT 1
        )
        WHERE EXISTS (
            SELECT 1
            FROM index_versions AS indexes
            WHERE indexes.knowledge_set_id = sets.id
              AND indexes.status = 'succeeded'
        )
        """
    )


def downgrade():
    op.drop_constraint(
        "fk_knowledge_set_current_index_project", "knowledge_sets", type_="foreignkey"
    )
    op.drop_column("knowledge_sets", "current_ready_index_id")
    op.drop_index("uq_index_active_knowledge_set", table_name="index_versions")
    op.drop_index("ix_indexes_knowledge_set_created", table_name="index_versions")
    op.drop_constraint(
        "uq_index_knowledge_set_version", "index_versions", type_="unique"
    )
    op.drop_constraint(
        "fk_index_knowledge_set_project", "index_versions", type_="foreignkey"
    )
    op.create_unique_constraint(
        "uq_index_version", "index_versions", ["project_id", "version"]
    )
    op.create_index(
        "uq_index_active_project",
        "index_versions",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued','running')"),
    )
    op.drop_column("index_versions", "knowledge_set_id")
    op.drop_index("ix_knowledge_sets_project_created", table_name="knowledge_sets")
    op.drop_table("knowledge_sets")
