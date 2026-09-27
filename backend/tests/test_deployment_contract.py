from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.deployment import (
    DeploymentCreate,
    LimitsInput,
    PromotionInput,
    QuestionInput,
)


def test_deployment_contract_rejects_extra_and_invalid_fields():
    ids = dict(pipeline_id=uuid4(), pipeline_version_id=uuid4(), index_id=uuid4())
    assert DeploymentCreate(name="Support", **ids).name == "Support"
    with pytest.raises(ValidationError):
        DeploymentCreate(name="Support", unknown=True, **ids)
    with pytest.raises(ValidationError):
        PromotionInput(release_id=uuid4(), reason=" ")
    with pytest.raises(ValidationError):
        QuestionInput(question=" " * 20)
    with pytest.raises(ValidationError):
        QuestionInput(question="x" * 8001)


def test_development_limits_are_bounded_and_hierarchical():
    values = dict(
        rate_per_minute=10,
        concurrent_runs=1,
        queued_runs=5,
        daily_budget_usd=Decimal("1"),
        monthly_budget_usd=Decimal("2"),
    )
    limits = LimitsInput(**values)
    assert limits.daily_budget_usd == Decimal("1")
    with pytest.raises(ValidationError):
        LimitsInput(**{**values, "rate_per_minute": 0})
    with pytest.raises(ValidationError):
        LimitsInput(**{**values, "daily_budget_usd": Decimal("3")})
