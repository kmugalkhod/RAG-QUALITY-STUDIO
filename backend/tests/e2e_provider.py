"""TEST STACK ONLY: deterministic HTTP transport. Never imported by app code."""

import json
import sys
import httpx
from app.providers.openrouter import OpenRouterEmbeddings
from app.providers import embeddings, generation
from app.main import app  # noqa: F401


def respond(request):
    body = json.loads(request.content)
    data = []
    for index, value in enumerate(body["input"]):
        vector = [0.0] * body["dimensions"]
        vector[0 if "orchard" in value.lower() else 1] = 1.0
        data.append({"index": index, "embedding": vector})
    return httpx.Response(200, json={"model": body["model"], "data": data})


original = embeddings.provider_for


def test_provider(config):
    original(config)  # Keep real configuration compatibility checks.
    return OpenRouterEmbeddings(config, transport=httpx.MockTransport(respond))


embeddings.provider_for = test_provider

if __name__ == "__main__" and sys.argv[-1] == "worker":
    from app.workers.celery_app import celery

    celery.worker_main(["worker", "--loglevel=warning", "--concurrency=2"])


def chat_respond(request):
    body = json.loads(request.content)
    question = json.loads(body["messages"][-1]["content"])["question"]
    answer = (
        "INSUFFICIENT_EVIDENCE: The sources do not give a launch code."
        if "launch code" in question.lower()
        else "The orchard grows apples. [S1]"
    )
    return httpx.Response(
        200,
        json={
            "model": body["model"],
            "choices": [{"finish_reason": "stop", "message": {"content": answer}}],
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 12,
                "total_tokens": 132,
            },
        },
    )


generation.provider_for = lambda: generation.OpenRouterChat(
    httpx.MockTransport(chat_respond)
)
