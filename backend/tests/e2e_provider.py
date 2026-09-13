"""TEST STACK ONLY: deterministic HTTP transport. Never imported by app code."""

from app.evaluation import evaluator
import json
import sys
import httpx
from app.connectors.base import ConnectorFailure, ConnectorIssue
from app.connectors.safe_http import SafeHttpClient
from app.connectors.website import WebsiteConnector
from app.connectors.s3 import S3ConnectionResult, S3Connector
from app.connectors import s3 as s3_module
from app.providers.openrouter import OpenRouterEmbeddings
from app.providers import embeddings, generation
from app.workers import ingestion as ingestion_worker, previews
from app.main import app  # noqa: F401
from datetime import UTC, datetime
from pathlib import Path


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
        else (
            "The controlled guide documents solar orchards. [S1]"
            if "controlled guide" in question.lower()
            else "The orchard grows apples. [S1]"
        )
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
            {"content-type": "text/html", "etag": '"home-v1"'},
            b"<main><h1>Controlled website</h1><p>The controlled site catalogs research.</p><a href='/guide'>Guide</a><a href='/guide#copy'>Copy</a><a href='/private'>Private</a><a href='https://elsewhere.example/out'>Out</a></main>",
        ),
        "https://controlled.example/guide": (
            200,
            {"content-type": "text/html", "etag": '"guide-v1"'},
            b"<main><h1>Controlled guide</h1><p>The controlled guide documents solar orchards.</p></main>",
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


def website_connector():
    return WebsiteConnector(
        client=SafeHttpClient(resolver=website_resolver, transport=WebsiteTransport()),
        sleeper=lambda _: None,
    )


previews.WebsiteConnector = website_connector
ingestion_worker.WebsiteConnector = website_connector


S3_STATE = Path("/data/documents/.s3-fixture-state")
S3_NOW = datetime(2026, 9, 13, tzinfo=UTC)
S3_OBJECTS = {
    "first": {
        "docs/orchard.txt": (
            b"The controlled S3 orchard grows apples in carefully managed research rows. "
            * 3,
            "orchard-v1",
            "version-orchard-1",
        ),
        "docs/old.txt": (
            b"This controlled S3 object will be removed during the next refresh. " * 3,
            "old-v1",
            "version-old-1",
        ),
    },
    "second": {
        "docs/orchard.txt": (
            b"The controlled S3 orchard grows apples in carefully managed research rows. "
            * 3,
            "orchard-v1",
            "version-orchard-1",
        ),
        "docs/new.txt": (
            b"The controlled S3 packing guide requires recycled paper boxes for apples. "
            * 3,
            "new-v1",
            "version-new-1",
        ),
    },
}


class S3Body:
    def __init__(self, content):
        self.content = content

    def read(self, limit):
        return self.content[:limit]

    def close(self):
        pass


class S3Transport:
    def state(self):
        try:
            return S3_STATE.read_text().strip()
        except OSError:
            return "first"

    def objects(self):
        state = self.state()
        if state == "denied":
            from botocore.exceptions import ClientError

            raise ClientError(
                {
                    "Error": {"Code": "AccessDenied", "Message": "fixture denied"},
                    "ResponseMetadata": {"HTTPStatusCode": 403},
                },
                "ListObjectsV2",
            )
        return S3_OBJECTS[state]

    def list_buckets(self, **kwargs):
        return {"Buckets": []}

    def list_objects_v2(self, **kwargs):
        return {
            "Contents": [
                {
                    "Key": key,
                    "Size": len(value[0]),
                    "ETag": f'"{value[1]}"',
                    "LastModified": S3_NOW,
                }
                for key, value in sorted(self.objects().items())
                if key.startswith(kwargs.get("Prefix", ""))
            ],
            "IsTruncated": False,
        }

    def head_object(self, **kwargs):
        value = self.objects()[kwargs["Key"]]
        return {
            "ContentLength": len(value[0]),
            "ETag": f'"{value[1]}"',
            "LastModified": S3_NOW,
            "VersionId": value[2],
        }

    def get_object(self, **kwargs):
        value = self.objects()[kwargs["Key"]]
        return {"Body": S3Body(value[0]), **self.head_object(**kwargs)}


s3_transport = S3Transport()


def s3_connector(credentials):
    return S3Connector(
        credentials,
        client_factory=lambda credentials, region, timeout: s3_transport,
    )


class S3Tester:
    def check(self, credentials):
        return S3ConnectionResult("succeeded", "ok")


s3_module.S3ConnectionTester = S3Tester
previews.S3Connector = s3_connector
ingestion_worker.S3Connector = s3_connector


@app.post("/api/test/s3-state/{state}")
def set_s3_state(state: str):
    if state not in {"first", "second", "denied"}:
        return {"updated": False}
    S3_STATE.parent.mkdir(parents=True, exist_ok=True)
    S3_STATE.write_text(state)
    return {"updated": True}


if __name__ == "__main__" and sys.argv[-1] == "worker":
    from app.workers.celery_app import celery

    celery.worker_main(["worker", "--loglevel=warning", "--concurrency=2"])
