"""Durable deployed runs and organization reservation ledger."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

U = sa.Uuid()
T = sa.DateTime(timezone=True)
M = sa.Numeric(12, 6)


def upgrade():
    op.create_table(
        "deployed_answer_runs",
        sa.Column("id", U, primary_key=True),
        sa.Column("organization_id", sa.String(100), nullable=False),
        sa.Column("project_id", U, nullable=False),
        sa.Column("deployment_id", U, nullable=False),
        sa.Column("release_id", U, nullable=False),
        sa.Column("key_id", U, nullable=False),
        sa.Column("client_id", U, nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("question", sa.String(8000)),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("stage", sa.String(40), nullable=False, server_default="admitted"),
        sa.Column("answer", sa.String()),
        sa.Column("citations", JSONB()),
        sa.Column("evidence", JSONB()),
        sa.Column("usage", JSONB()),
        sa.Column("timing_ms", JSONB()),
        sa.Column("error_code", sa.String(80)),
        sa.Column("error_message", sa.String(500)),
        sa.Column("cost_reservation_usd", M, nullable=False),
        sa.Column("provider_cost_usd", M),
        sa.Column("cost_basis_version", sa.String(80), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("execution_token", U),
        sa.Column("provider_call_started_at", T),
        sa.Column("heartbeat_at", T),
        sa.Column("deadline_at", T),
        sa.Column("dispatched_at", T),
        sa.Column("started_at", T),
        sa.Column("finished_at", T),
        sa.Column("cancel_requested_at", T),
        sa.Column("result_expires_at", T, nullable=False),
        sa.Column("redacted_at", T),
        sa.Column("created_at", T, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["deployment_id", "organization_id", "project_id"],
            [
                "answer_deployments.id",
                "answer_deployments.organization_id",
                "answer_deployments.project_id",
            ],
            name="fk_deployed_run_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "deployment_id"],
            [
                "answer_deployment_releases.id",
                "answer_deployment_releases.deployment_id",
            ],
            name="fk_deployed_run_release",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["key_id", "deployment_id"],
            ["answer_deployment_keys.id", "answer_deployment_keys.deployment_id"],
            name="fk_deployed_run_key",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "deployment_id",
            "client_id",
            "idempotency_key",
            name="uq_deployed_run_idempotency",
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','insufficient_evidence','failed','cancel_requested','cancelled')",
            name="ck_deployed_run_status",
        ),
        sa.CheckConstraint(
            "cost_reservation_usd >= 0", name="ck_deployed_run_reservation"
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_deployed_run_attempts"),
    )
    op.create_index(
        "ix_deployed_run_history",
        "deployed_answer_runs",
        ["deployment_id", "created_at", "id"],
    )
    op.create_index(
        "ix_deployed_run_org_status",
        "deployed_answer_runs",
        ["organization_id", "status", "created_at"],
    )
    op.create_index(
        "ix_deployed_run_queue", "deployed_answer_runs", ["status", "dispatched_at"]
    )
    op.create_table(
        "deployment_usage_buckets",
        sa.Column("id", U, primary_key=True),
        sa.Column("organization_id", sa.String(100), nullable=False),
        sa.Column("period", sa.String(8), nullable=False),
        sa.Column("period_start", T, nullable=False),
        sa.Column("accepted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved_usd", M, nullable=False, server_default="0"),
        sa.Column("settled_usd", M, nullable=False, server_default="0"),
        sa.Column("updated_at", T, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "organization_id",
            "period",
            "period_start",
            name="uq_deployment_usage_period",
        ),
        sa.CheckConstraint(
            "period IN ('day','month')", name="ck_deployment_usage_period"
        ),
        sa.CheckConstraint(
            "reserved_usd >= 0 AND settled_usd >= 0 AND accepted_count >= 0",
            name="ck_deployment_usage_amounts",
        ),
    )
    op.create_table(
        "deployment_usage_entries",
        sa.Column("id", U, primary_key=True),
        sa.Column("run_id", U, nullable=False),
        sa.Column("organization_id", sa.String(100), nullable=False),
        sa.Column("entry_type", sa.String(16), nullable=False),
        sa.Column("amount_usd", M, nullable=False),
        sa.Column("basis", sa.String(100), nullable=False),
        sa.Column("created_at", T, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["run_id"], ["deployed_answer_runs.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("run_id", "entry_type", name="uq_deployment_usage_entry"),
        sa.CheckConstraint(
            "entry_type IN ('reservation','settlement','release')",
            name="ck_deployment_usage_entry_type",
        ),
        sa.CheckConstraint("amount_usd >= 0", name="ck_deployment_usage_entry_amount"),
    )


def downgrade():
    for table in (
        "deployment_usage_entries",
        "deployment_usage_buckets",
        "deployed_answer_runs",
    ):
        if op.get_bind().scalar(sa.text(f"SELECT count(*) FROM {table}")):
            raise RuntimeError("Deployed answer history cannot be dropped.")
    op.drop_table("deployment_usage_entries")
    op.drop_table("deployment_usage_buckets")
    op.drop_table("deployed_answer_runs")
