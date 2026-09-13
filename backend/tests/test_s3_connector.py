from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError
from pydantic import ValidationError

from app.connectors.base import ConnectorFailure
from app.connectors.s3 import S3ConnectionTester, S3Connector
from app.schemas.ingestion import S3Config


NOW = datetime(2026, 9, 13, tzinfo=UTC)
CREDS = {
    "kind": "s3",
    "access_key_id": "fixture-access",
    "secret_access_key": "fixture-secret",
    "session_token": None,
}


class Body:
    def __init__(self, value):
        self.value = value
        self.closed = False

    def read(self, limit):
        return self.value[:limit]

    def close(self):
        self.closed = True


class S3Double:
    def __init__(self):
        self.calls = []
        self.pages = [
            {
                "Contents": [
                    {"Key": "docs/", "Size": 0, "LastModified": NOW},
                    {"Key": "docs/ignore.md", "Size": 20, "LastModified": NOW},
                    {
                        "Key": "docs/guide.txt",
                        "Size": 18,
                        "ETag": '"guide-etag"',
                        "LastModified": NOW,
                    },
                    {
                        "Key": "docs/archive.pdf",
                        "Size": 100,
                        "StorageClass": "GLACIER",
                        "LastModified": NOW,
                    },
                ],
                "IsTruncated": True,
                "NextContinuationToken": "next-safe-token",
            },
            {
                "Contents": [
                    {
                        "Key": "docs/manual.pdf",
                        "Size": 7,
                        "ETag": '"manual-etag"',
                        "LastModified": NOW,
                    }
                ],
                "IsTruncated": False,
            },
        ]
        self.heads = {
            "docs/guide.txt": {
                "ETag": '"guide-etag"',
                "ContentLength": 18,
                "LastModified": NOW,
                "VersionId": "guide-v1",
            },
            "docs/manual.pdf": {
                "ETag": '"manual-etag"',
                "ContentLength": 7,
                "LastModified": NOW,
            },
        }
        self.objects = {
            "docs/guide.txt": b"Orchard guide text",
            "docs/manual.pdf": b"pdfdata",
        }

    def list_buckets(self, **kwargs):
        self.calls.append(("list_buckets", kwargs))
        return {"Buckets": []}

    def list_objects_v2(self, **kwargs):
        self.calls.append(("list", kwargs))
        index = 1 if kwargs.get("ContinuationToken") else 0
        return self.pages[index]

    def head_object(self, **kwargs):
        self.calls.append(("head", kwargs))
        return self.heads[kwargs["Key"]]

    def get_object(self, **kwargs):
        self.calls.append(("get", kwargs))
        key = kwargs["Key"]
        value = self.objects[key]
        head = self.heads[key]
        return {"Body": Body(value), **head}


def config(**changes):
    values = {
        "kind": "s3",
        "connection_id": uuid4(),
        "region": "us-east-1",
        "bucket": "research-archive",
        "prefix": "docs/",
        "expected_bucket_owner": "123456789012",
        "allowed_file_types": ["txt", "pdf"],
        "max_objects": 10,
        "max_pages": 2,
        "max_object_bytes": 1024,
        "max_total_bytes": 2048,
        "request_timeout_seconds": 4,
    }
    values.update(changes)
    return S3Config.model_validate(values)


def factory(double, captured):
    def create(credentials, region, timeout):
        captured.append((credentials, region, timeout))
        return double

    return create


def test_paginated_discovery_filters_and_carries_versioned_provenance():
    double, captured = S3Double(), []
    connector = S3Connector(CREDS, client_factory=factory(double, captured))
    outcomes = connector.discover_all(config())
    assert [(item.external_id, item.status) for item in outcomes] == [
        ("docs/", "excluded"),
        ("docs/archive.pdf", "excluded"),
        ("docs/guide.txt", "included"),
        ("docs/ignore.md", "excluded"),
        ("docs/manual.pdf", "included"),
    ]
    lists = [call for call in double.calls if call[0] == "list"]
    assert lists[1][1]["ContinuationToken"] == "next-safe-token"
    assert all(call[1]["ExpectedBucketOwner"] == "123456789012" for call in lists)
    assert all(value[0] == CREDS for value in captured)
    assert all(value[1:] == ("us-east-1", 4.0) for value in captured)
    guide = next(item for item in outcomes if item.external_id == "docs/guide.txt")
    manual = next(item for item in outcomes if item.external_id == "docs/manual.pdf")
    assert guide.provider_revision == "version:guide-v1"
    assert manual.provider_revision.startswith("etag:manual-etag;size:7;modified:")


def test_exact_version_fetch_and_unchanged_shortcut():
    double = S3Double()
    connector = S3Connector(
        CREDS, client_factory=factory(double, []), clock=lambda: NOW
    )
    parsed = config()
    _, artifacts = connector.fetch_all(parsed, {}, "a" * 64)
    guide = next(
        item for item in artifacts if item.item.external_id.endswith("guide.txt")
    )
    assert guide.content == b"Orchard guide text"
    get_call = next(
        call
        for call in double.calls
        if call[0] == "get" and call[1]["Key"].endswith("guide.txt")
    )
    assert get_call[1]["VersionId"] == "guide-v1"
    assert "IfMatch" not in get_call[1]
    manual_get = next(
        call
        for call in double.calls
        if call[0] == "get" and call[1]["Key"].endswith("manual.pdf")
    )
    assert manual_get[1]["IfMatch"] == "manual-etag"
    assert "VersionId" not in manual_get[1]

    prior = SimpleNamespace(
        provider_revision=guide.item.provider_revision,
        processing_config_hash="a" * 64,
        content_hash=guide.content_hash,
    )
    double.calls.clear()
    _, refreshed = connector.fetch_all(
        parsed, {guide.item.canonical_location: prior}, "a" * 64
    )
    same = next(
        item for item in refreshed if item.item.external_id.endswith("guide.txt")
    )
    assert same.unchanged and same.content is None
    assert not any(
        call[0] == "get" and call[1]["Key"].endswith("guide.txt")
        for call in double.calls
    )


def test_fetch_rejects_an_object_that_changes_after_discovery():
    double = S3Double()
    connector = S3Connector(CREDS, client_factory=factory(double, []))
    parsed = config()
    item = connector.discover(parsed, "next-safe-token").items[0]
    double.heads["docs/manual.pdf"]["ETag"] = '"changed-etag"'
    with pytest.raises(ConnectorFailure) as failure:
        connector.fetch(parsed, item)
    assert failure.value.issue.code == "object_changed"


def test_connection_and_provider_failures_are_sanitized():
    captured = []
    ok = S3ConnectionTester(factory(S3Double(), captured)).check(CREDS)
    assert (ok.outcome, ok.code) == ("succeeded", "ok")
    assert captured[0] == (CREDS, "us-east-1", 10)

    class Denied:
        def list_objects_v2(self, **kwargs):
            raise ClientError(
                {
                    "Error": {
                        "Code": "AccessDenied",
                        "Message": "echo fixture-secret",
                    },
                    "ResponseMetadata": {"HTTPStatusCode": 403},
                },
                "ListObjectsV2",
            )

    with pytest.raises(ConnectorFailure) as failure:
        S3Connector(CREDS, client_factory=factory(Denied(), [])).discover_all(config())
    assert failure.value.issue.code == "permission_denied"
    assert "fixture-secret" not in failure.value.issue.message


def test_schema_rejects_unsafe_or_unbounded_selection():
    with pytest.raises(ValidationError):
        config(bucket="127.0.0.1")
    with pytest.raises(ValidationError):
        config(allowed_file_types=["txt", "txt"])
    with pytest.raises(ValidationError):
        config(max_object_bytes=2048, max_total_bytes=1024)
