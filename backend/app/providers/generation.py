"""Application-owned single-turn generation contract and OpenRouter adapter."""

import json
import math
import time
from dataclasses import dataclass
from typing import Protocol

import httpx
from app.core.config import settings
from app.providers.rate_limit import reserve_request


class GenerationError(Exception):
    pass


@dataclass(frozen=True)
class Completion:
    answer: str
    model: str
    usage: dict | None
    cost_usd: float | None
    finish_reason: str = "stop"


class AnswerProvider(Protocol):
    def generate(self, messages: list[dict], config: dict) -> Completion: ...


def allowed_models():
    return list(
        dict.fromkeys(
            [
                m
                for m in [settings.chat_model, *settings.chat_models]
                if m and "embedding" not in m.lower()
            ]
        )
    )


def configured(model=None, max_tokens=None, temperature=0):
    if not settings.chat_model or "embedding" in settings.chat_model.lower():
        raise GenerationError(
            "Configure CHAT_MODEL with an OpenRouter chat model ID on the server."
        )
    if not settings.openrouter_api_key.get_secret_value():
        raise GenerationError("Configure server-side OPENROUTER_API_KEY.")
    if settings.chat_max_tokens + 1024 >= settings.chat_context_tokens:
        raise GenerationError(
            "CHAT_CONTEXT_TOKENS must leave room for the prompt and reserved output."
        )
    model = model or settings.chat_model
    if model not in allowed_models():
        raise GenerationError("Select a server-configured chat model.")
    max_tokens = max_tokens if max_tokens is not None else settings.chat_max_tokens
    if max_tokens + 1024 >= settings.chat_context_tokens:
        raise GenerationError(
            "Output capacity must leave room for the prompt in the server context budget."
        )
    return dict(
        provider="openrouter",
        model=model,
        context_tokens=settings.chat_context_tokens,
        max_tokens=max_tokens,
        temperature=temperature,
        context_accounting="utf8-bytes-plus-256-envelope-v1",
    )


def provider_for() -> AnswerProvider:
    return OpenRouterChat()


class OpenRouterChat:
    def __init__(self, transport=None):
        self.transport = transport

    def generate(self, messages, config):
        reserve_request()
        # No automatic retry: an ambiguous completion may already be billed.
        deadline = time.monotonic() + 55
        try:
            with httpx.Client(
                timeout=httpx.Timeout(45, connect=5),
                transport=self.transport,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                with client.stream(
                    "POST",
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": "Bearer "
                        + settings.openrouter_api_key.get_secret_value()
                    },
                    json={
                        "model": config["model"],
                        "messages": messages,
                        "max_tokens": config["max_tokens"],
                        "temperature": config["temperature"],
                        "stream": False,
                        "provider": {"allow_fallbacks": False},
                    },
                ) as response:
                    if response.status_code != 200:
                        message = {
                            401: "credentials rejected",
                            403: "model access denied",
                            402: "insufficient credits",
                            429: "rate limit reached",
                        }.get(
                            response.status_code,
                            "request failed or service unavailable",
                        )
                        raise GenerationError(
                            f"OpenRouter generation: {message}. Check server configuration and retry manually."
                        )
                    body = bytearray()
                    for block in response.iter_bytes():
                        body.extend(block)
                        if len(body) > 1_000_000 or time.monotonic() > deadline:
                            raise GenerationError(
                                "OpenRouter generation exceeded response size or duration limits."
                            )
            data = json.loads(body)
            choice = data["choices"][0]
            answer = choice["message"]["content"]
            finish_reason = choice.get("finish_reason", "unknown")
            if not isinstance(data["model"], str) or not isinstance(finish_reason, str):
                raise ValueError()
            if finish_reason == "stop" and (
                not isinstance(answer, str) or not answer.strip()
            ):
                raise ValueError()
            if not isinstance(answer, str):
                answer = ""
            raw_usage = data.get("usage")
            usage = None
            cost = None
            if isinstance(raw_usage, dict):
                usage = {
                    k: v
                    for k, v in raw_usage.items()
                    if k in {"prompt_tokens", "completion_tokens", "total_tokens"}
                    and type(v) is int
                    and v >= 0
                }
                value = raw_usage.get("cost")
                if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                    cost = value
            return Completion(answer.strip(), data["model"], usage, cost, finish_reason)
        except httpx.HTTPError:
            raise GenerationError(
                "OpenRouter generation connection unavailable or timed out. Retry manually."
            ) from None
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise GenerationError(
                "OpenRouter returned a malformed generation response."
            ) from None
