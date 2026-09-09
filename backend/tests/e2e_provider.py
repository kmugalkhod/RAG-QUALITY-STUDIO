"""TEST STACK ONLY: deterministic HTTP transport. Never imported by app code."""

import json
import sys
import httpx
from app.providers.openrouter import OpenRouterEmbeddings
from app.providers import embeddings
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
