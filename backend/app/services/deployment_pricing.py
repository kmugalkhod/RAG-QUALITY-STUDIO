"""Approved upper-bound price arithmetic for admission reservations."""

from decimal import Decimal, ROUND_UP
from fastapi import HTTPException

from app.core.config import settings
from app.schemas.pipeline import Execution

MILLION = Decimal("1000000")
CENTI_MICRO = Decimal("0.000001")


def worst_case(
    execution: Execution, embedding_config: dict, question_bytes: int
) -> Decimal:
    if not settings.deployment_pricing_version:
        raise HTTPException(503, "Approved deployment pricing is unavailable.")
    llm = next(node for node in execution.nodes if node.type == "llm")
    generation = settings.deployment_approved_prices.get(llm.model, {})
    embedding = settings.deployment_approved_prices.get(
        embedding_config.get("model"), {}
    )
    try:
        input_price = Decimal(generation["input_per_million_usd"])
        output_price = Decimal(generation["output_per_million_usd"])
        embedding_price = Decimal(embedding["input_per_million_usd"])
    except (KeyError, TypeError, ValueError, ArithmeticError):
        raise HTTPException(
            503, "Approved deployment pricing is unavailable."
        ) from None
    if min(input_price, output_price, embedding_price) <= 0:
        raise HTTPException(503, "Approved deployment pricing is unavailable.")
    context_input = max(settings.chat_context_tokens - llm.max_tokens, 0)
    amount = (
        input_price * Decimal(context_input)
        + output_price * Decimal(llm.max_tokens)
        + embedding_price * Decimal(question_bytes)
    ) / MILLION
    amount = amount.quantize(CENTI_MICRO, rounding=ROUND_UP)
    if amount > settings.deployment_max_reserved_usd_per_run:
        raise HTTPException(402, "This model exceeds the per-request spending ceiling.")
    return amount
