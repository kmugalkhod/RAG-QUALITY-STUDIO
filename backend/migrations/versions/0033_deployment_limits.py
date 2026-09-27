"""Per-deployment ceilings constrained by operator settings."""

from alembic import op
import sqlalchemy as sa

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade():
    for name, typ, default in (
        ("rate_per_minute", sa.Integer(), "30"),
        ("concurrent_runs", sa.Integer(), "2"),
        ("queued_runs", sa.Integer(), "20"),
        ("daily_budget_usd", sa.Numeric(12, 6), "5"),
        ("monthly_budget_usd", sa.Numeric(12, 6), "20"),
    ):
        op.add_column(
            "answer_deployments",
            sa.Column(name, typ, nullable=False, server_default=default),
        )
    op.create_check_constraint(
        "ck_answer_deployment_limits",
        "answer_deployments",
        "rate_per_minute > 0 AND concurrent_runs > 0 AND queued_runs > 0 "
        "AND daily_budget_usd > 0 AND monthly_budget_usd > 0",
    )


def downgrade():
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM answer_deployments)")):
        raise RuntimeError(
            "Deployment limits are retained while deployment data exists."
        )
    op.drop_constraint("ck_answer_deployment_limits", "answer_deployments")
    for name in (
        "monthly_budget_usd",
        "daily_budget_usd",
        "queued_runs",
        "concurrent_runs",
        "rate_per_minute",
    ):
        op.drop_column("answer_deployments", name)
