"""TEST STACK ONLY: deterministic HTTP transport. Never imported by app code."""

from app.evaluation import evaluator
import json
import sys
import httpx
from app.connectors.base import ConnectorFailure, ConnectorIssue
from app.connectors.safe_http import SafeHttpClient
from app.connectors.website import WebsiteConnector
from app.providers.openrouter import OpenRouterEmbeddings
from app.providers import embeddings, generation
from app.workers import previews
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


class FixtureJudge:
    def score(self, metric, row, output, guard=None):
        if guard:
            guard()
        blocked = evaluator.precondition(metric, row, output)
        if blocked:
            return blocked
        return {
            "status": "succeeded",
            "value": 0.8,
            "reason": "Deterministic browser fixture",
            "evaluation_cost_usd": None,
            "calls": [],
        }


evaluator.provider_for = lambda config: FixtureJudge()


def website_resolver(host, port, type):
    return [(2, type, 6, "", ("93.184.216.34", port))]


class WebsiteTransport:
    responses = {
        "https://controlled.example/robots.txt": (
            200,
            {"content-type": "text/plain"},
            b"User-agent: *\nDisallow: /private\n",
        ),
        "https://controlled.example/": (
            200,
            {"content-type": "text/html"},
            b"<a href='/guide'>Guide</a><a href='/guide#copy'>Copy</a><a href='/private'>Private</a><a href='https://elsewhere.example/out'>Out</a>",
        ),
        "https://controlled.example/guide": (
            200,
            {"content-type": "text/html"},
            b"<h1>Controlled guide</h1>",
        ),
    }

    def request(self, url, address, timeout, headers, max_bytes):
        response = self.responses.get(url)
        if response is None:
            raise ConnectorFailure(
                ConnectorIssue(
                    code="controlled_missing",
                    message="The controlled browser fixture has no response for this URL.",
                    retryable=False,
                )
            )
        return response


previews.WebsiteConnector = lambda: WebsiteConnector(
    client=SafeHttpClient(resolver=website_resolver, transport=WebsiteTransport()),
    sleeper=lambda _: None,
)

if __name__ == "__main__" and sys.argv[-1] == "worker":
    from app.workers.celery_app import celery

    celery.worker_main(["worker", "--loglevel=warning", "--concurrency=2"])
