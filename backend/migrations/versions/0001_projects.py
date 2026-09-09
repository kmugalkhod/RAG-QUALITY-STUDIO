"""Create projects."""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(btrim(name)) BETWEEN 1 AND 120", name="ck_projects_name"
        ),
        sa.CheckConstraint(
            "char_length(description) <= 2000", name="ck_projects_description"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_created_id", "projects", ["created_at", "id"])


def downgrade():
    op.drop_table("projects")
