"""Bounded Amazon S3 discovery, validation and exact-object fetching."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any, Callable
from urllib.parse import quote

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectTimeoutError,
    ConnectionClosedError,
    EndpointConnectionError,
    ReadTimeoutError,
)

from app.connectors.base import (
    ConnectionCheck,
    ConnectorFailure,
    ConnectorIssue,
    DiscoveredItem,
    DiscoveryFailure,
    DiscoveryPage,
)
from app.schemas.ingestion import S3Config


AUTH_CODES = {
    "AuthFailure",
    "ExpiredToken",
    "InvalidAccessKeyId",
    "InvalidClientTokenId",
    "InvalidToken",
    "SignatureDoesNotMatch",
    "TokenRefreshRequired",
}
DENIED_CODES = {"AccessDenied", "AllAccessDisabled", "Forbidden"}
MISSING_CODES = {"NoSuchBucket", "NoSuchKey", "NotFound", "NoSuchVersion"}
THROTTLED_CODES = {
    "SlowDown",
    "Throttling",
    "ThrottlingException",
    "RequestLimitExceeded",
}
NETWORK_ERRORS = (
    ConnectTimeoutError,
    ConnectionClosedError,
    EndpointConnectionError,
    ReadTimeoutError,
)
MEDIA_TYPES = {
    "txt": "text/plain",
    "pdf": "application/pdf",
    "md": "text/markdown",
    "html": "text/html",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
ARCHIVED_CLASSES = {"GLACIER", "DEEP_ARCHIVE"}


@dataclass(frozen=True)
class S3PreviewOutcome:
    external_id: str | None
    display_name: str
    canonical_location: str | None
    provider_revision: str | None
    media_type: str | None
    status: str
    reason: str
    size_bytes: int | None = None
    depth: int | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class S3Artifact:
    item: DiscoveredItem
    content: bytes | None
    content_hash: str | None
    fetched_at: datetime
    unchanged: bool = False


@dataclass(frozen=True)
class S3ConnectionResult:
    outcome: str
    code: str


def _issue(exc: Exception, *, operation: str) -> ConnectorIssue:
    if isinstance(exc, ClientError):
        code = str(exc.response.get("Error", {}).get("Code", ""))
        status = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))
        if code in AUTH_CODES:
            return ConnectorIssue(
                code="authentication_failed",
                message="Amazon S3 rejected the configured credentials.",
                retryable=False,
            )
        if code in DENIED_CODES or status in (401, 403):
            return ConnectorIssue(
                code="permission_denied",
                message=f"Amazon S3 denied permission to {operation}.",
                retryable=False,
            )
        if code in MISSING_CODES or status == 404:
            return ConnectorIssue(
                code="not_found",
                message="The selected S3 bucket or object is no longer available.",
                retryable=False,
            )
        if code in THROTTLED_CODES or status == 429:
            return ConnectorIssue(
                code="provider_throttled",
                message="Amazon S3 temporarily limited this request.",
                retryable=True,
            )
        if status >= 500:
            return ConnectorIssue(
                code="provider_unavailable",
                message="Amazon S3 is temporarily unavailable.",
                retryable=True,
            )
    if isinstance(exc, NETWORK_ERRORS):
        return ConnectorIssue(
            code="endpoint_unreachable",
            message="Amazon S3 could not be reached within the configured timeout.",
            retryable=True,
        )
    return ConnectorIssue(
        code="provider_error",
        message="Amazon S3 could not complete the requested operation.",
        retryable=isinstance(exc, BotoCoreError),
    )


def _raise_safe(exc: Exception, *, operation: str):
    raise ConnectorFailure(_issue(exc, operation=operation)) from None


def _client(credentials: dict, region: str, timeout: float):
    return boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=credentials["access_key_id"],
        aws_secret_access_key=credentials["secret_access_key"],
        aws_session_token=credentials.get("session_token"),
        config=Config(
            connect_timeout=timeout,
            read_timeout=timeout,
            retries={"mode": "standard", "total_max_attempts": 3},
        ),
    )


def _modified(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _location(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{quote(key, safe='/')}"


def _revision(version_id: str | None, etag: str, size: int, modified: datetime | None):
    if version_id and version_id != "null":
        return f"version:{version_id}"
    stamp = modified.isoformat() if modified else "unknown"
    return f"etag:{etag};size:{size};modified:{stamp}"


class S3ConnectionTester:
    def __init__(self, client_factory: Callable = _client):
        self.client_factory = client_factory

    def check(self, credentials: dict):
        try:
            client = self.client_factory(credentials, "us-east-1", 10)
            client.list_buckets(MaxBuckets=1)
        except Exception as exc:
            issue = _issue(exc, operation="list buckets")
            code = (
                issue.code
                if issue.code
                in {
                    "authentication_failed",
                    "permission_denied",
                    "endpoint_unreachable",
                }
                else "endpoint_unreachable"
            )
            return S3ConnectionResult("failed", code)
        return S3ConnectionResult("succeeded", "ok")


class S3Connector:
    kind = "s3"
    config_version = "1"

    def __init__(
        self,
        credentials: dict,
        *,
        client_factory: Callable = _client,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        if credentials.get("kind") != "s3":
            raise ConnectorFailure(
                ConnectorIssue(
                    code="connection_kind_mismatch",
                    message="The selected source connection is not an S3 connection.",
                    retryable=False,
                )
            )
        self.credentials = credentials
        self.client_factory = client_factory
        self.clock = clock

    def validate(self, config: object, connection: object | None = None) -> None:
        S3Config.model_validate(config)

    def test_connection(self, connection: object | None = None) -> ConnectionCheck:
        result = S3ConnectionTester(self.client_factory).check(self.credentials)
        if result.outcome == "succeeded":
            return ConnectionCheck(
                status="available", message="Amazon S3 is reachable."
            )
        return ConnectionCheck(
            status="unavailable", message="Amazon S3 is unavailable."
        )

    def _api(self, config: S3Config):
        return self.client_factory(
            self.credentials, config.region, config.request_timeout_seconds
        )

    @staticmethod
    def _common(config: S3Config):
        return (
            {"ExpectedBucketOwner": config.expected_bucket_owner}
            if config.expected_bucket_owner
            else {}
        )

    def _item(self, config: S3Config, value: dict, head: dict) -> DiscoveredItem:
        key = str(value["Key"])
        size = int(value.get("Size", 0))
        etag = str(head.get("ETag") or value.get("ETag") or "").strip('"')
        modified = _modified(head.get("LastModified") or value.get("LastModified"))
        version_id = head.get("VersionId")
        return DiscoveredItem(
            external_id=key,
            display_name=PurePosixPath(key).name or key,
            canonical_location=_location(config.bucket, key),
            media_type=MEDIA_TYPES[key.rsplit(".", 1)[-1].lower()],
            provider_revision=_revision(version_id, etag, size, modified),
            modified_at=modified,
            metadata={
                "bucket": config.bucket,
                "key": key,
                "etag": etag,
                "size_bytes": size,
                "version_id": version_id,
                "storage_class": str(value.get("StorageClass", "STANDARD")),
                "connection_id": str(config.connection_id),
            },
        )

    def _discover_page(self, config: S3Config, cursor: str | None):
        client = self._api(config)
        args: dict[str, Any] = {
            "Bucket": config.bucket,
            "Prefix": config.prefix,
            "MaxKeys": min(1000, config.max_objects),
            **self._common(config),
        }
        if cursor:
            args["ContinuationToken"] = cursor
        try:
            response = client.list_objects_v2(**args)
        except Exception as exc:
            _raise_safe(exc, operation="list the selected bucket")
        return client, response

    def discover(self, config: object, cursor: str | None = None) -> DiscoveryPage:
        parsed = S3Config.model_validate(config)
        client, response = self._discover_page(parsed, cursor)
        items = []
        failures = []
        for value in sorted(
            response.get("Contents", ()), key=lambda row: row.get("Key", "")
        ):
            key = str(value.get("Key", ""))
            extension = key.rsplit(".", 1)[-1].lower() if "." in key else ""
            size = int(value.get("Size", 0))
            storage_class = str(value.get("StorageClass", "STANDARD"))
            if (
                not key
                or key.endswith("/")
                or extension not in parsed.allowed_file_types
                or size <= 0
                or size > parsed.max_object_bytes
                or storage_class in ARCHIVED_CLASSES
            ):
                continue
            try:
                head = client.head_object(
                    Bucket=parsed.bucket,
                    Key=key,
                    **self._common(parsed),
                )
                items.append(self._item(parsed, value, head))
            except Exception as exc:
                issue = _issue(exc, operation="read object metadata")
                failures.append(
                    DiscoveryFailure(
                        external_id=key,
                        canonical_location=_location(parsed.bucket, key),
                        error=issue,
                    )
                )
        return DiscoveryPage(
            items=tuple(items),
            failures=tuple(failures),
            next_cursor=response.get("NextContinuationToken")
            if response.get("IsTruncated")
            else None,
        )

    def discover_all(self, config: object) -> list[S3PreviewOutcome]:
        parsed = S3Config.model_validate(config)
        client = self._api(parsed)
        outcomes: list[S3PreviewOutcome] = []
        cursor = None
        scanned = 0
        transferred = 0
        for page_number in range(1, parsed.max_pages + 1):
            args: dict[str, Any] = {
                "Bucket": parsed.bucket,
                "Prefix": parsed.prefix,
                "MaxKeys": min(1000, parsed.max_objects - scanned),
                **self._common(parsed),
            }
            if cursor:
                args["ContinuationToken"] = cursor
            try:
                response = client.list_objects_v2(**args)
            except Exception as exc:
                _raise_safe(exc, operation="list the selected bucket")
            rows = sorted(
                response.get("Contents", ()), key=lambda row: row.get("Key", "")
            )
            for value in rows:
                scanned += 1
                key = str(value.get("Key", ""))
                size = int(value.get("Size", 0))
                extension = key.rsplit(".", 1)[-1].lower() if "." in key else ""
                location = _location(parsed.bucket, key) if key else None
                storage_class = str(value.get("StorageClass", "STANDARD"))
                status, reason, media, code = "included", "Ready to ingest.", None, None
                provider_revision = None
                if not key:
                    status, reason, code = (
                        "failed",
                        "S3 returned an invalid object key.",
                        "invalid_key",
                    )
                elif key.endswith("/"):
                    status, reason = "excluded", "S3 folder markers are not documents."
                elif extension not in parsed.allowed_file_types:
                    status, reason = (
                        "excluded",
                        "Object type is outside the TXT/PDF allowlist.",
                    )
                elif size <= 0:
                    status, reason = "excluded", "Empty S3 objects are not indexable."
                elif size > parsed.max_object_bytes:
                    status, reason = (
                        "excluded",
                        "Object exceeds the configured per-object byte limit.",
                    )
                elif storage_class in ARCHIVED_CLASSES:
                    status, reason = (
                        "excluded",
                        "Archived object must be restored before ingestion.",
                    )
                elif transferred + size > parsed.max_total_bytes:
                    status, reason = (
                        "excluded",
                        "Object would exceed the configured total byte limit.",
                    )
                else:
                    try:
                        head = client.head_object(
                            Bucket=parsed.bucket,
                            Key=key,
                            **self._common(parsed),
                        )
                        item = self._item(parsed, value, head)
                        media = item.media_type
                        provider_revision = item.provider_revision
                        transferred += size
                    except Exception as exc:
                        issue = _issue(exc, operation="read object metadata")
                        status, reason, code = "failed", issue.message, issue.code
                outcomes.append(
                    S3PreviewOutcome(
                        external_id=key or None,
                        display_name=PurePosixPath(key).name
                        or key
                        or "Invalid S3 object",
                        canonical_location=location,
                        provider_revision=provider_revision,
                        media_type=media,
                        status=status,
                        reason=reason,
                        size_bytes=size if key else None,
                        error_code=code,
                    )
                )
            truncated = bool(response.get("IsTruncated"))
            cursor = response.get("NextContinuationToken")
            if not truncated:
                return outcomes
            if not cursor:
                raise ConnectorFailure(
                    ConnectorIssue(
                        code="invalid_provider_page",
                        message="Amazon S3 returned an invalid discovery page.",
                        retryable=True,
                    )
                )
            if scanned >= parsed.max_objects:
                raise ConnectorFailure(
                    ConnectorIssue(
                        code="object_limit_exceeded",
                        message="S3 discovery exceeded the configured object limit.",
                        retryable=False,
                    )
                )
        raise ConnectorFailure(
            ConnectorIssue(
                code="page_limit_exceeded",
                message="S3 discovery exceeded the configured page limit.",
                retryable=False,
            )
        )

    def fetch(self, config: object, item: DiscoveredItem) -> S3Artifact:
        parsed = S3Config.model_validate(config)
        key = str(item.metadata["key"])
        expected_revision = item.provider_revision or ""
        args: dict[str, Any] = {
            "Bucket": parsed.bucket,
            "Key": key,
            **self._common(parsed),
        }
        version_id = item.metadata.get("version_id")
        if version_id and version_id != "null":
            args["VersionId"] = version_id
        elif item.metadata.get("etag"):
            args["IfMatch"] = str(item.metadata["etag"])
        try:
            response = self._api(parsed).get_object(**args)
            length = int(response.get("ContentLength", -1))
            if length <= 0 or length > parsed.max_object_bytes:
                raise ConnectorFailure(
                    ConnectorIssue(
                        code="object_size_changed",
                        message="The S3 object no longer fits the configured byte limit.",
                        retryable=False,
                    )
                )
            body = response["Body"]
            try:
                content = body.read(parsed.max_object_bytes + 1)
            finally:
                body.close()
            if len(content) != length or len(content) > parsed.max_object_bytes:
                raise ConnectorFailure(
                    ConnectorIssue(
                        code="object_size_changed",
                        message="The S3 object changed size while it was fetched.",
                        retryable=True,
                    )
                )
            actual = _revision(
                response.get("VersionId"),
                str(response.get("ETag", "")).strip('"'),
                length,
                _modified(response.get("LastModified")),
            )
            if actual != expected_revision:
                raise ConnectorFailure(
                    ConnectorIssue(
                        code="object_changed",
                        message="The S3 object changed after discovery. Retry the run.",
                        retryable=True,
                    )
                )
            return S3Artifact(
                item=item,
                content=content,
                content_hash=hashlib.sha256(content).hexdigest(),
                fetched_at=self.clock(),
            )
        except ConnectorFailure:
            raise
        except Exception as exc:
            _raise_safe(exc, operation="fetch the selected object")

    def fetch_all(
        self,
        config: object,
        priors: dict[str, object],
        processing_config_hash: str,
    ) -> tuple[list[S3PreviewOutcome], list[S3Artifact]]:
        parsed = S3Config.model_validate(config)
        outcomes = self.discover_all(parsed)
        artifacts = []
        for outcome in outcomes:
            if outcome.status != "included" or not outcome.canonical_location:
                continue
            # Recreate the authoritative item metadata from a bounded discovery page.
            # discover_all already performed HEAD; use discover() only in tests/protocol calls,
            # so fetch_all performs one exact lookup for the included key.
            client = self._api(parsed)
            key = outcome.external_id or ""
            try:
                head = client.head_object(
                    Bucket=parsed.bucket, Key=key, **self._common(parsed)
                )
            except Exception as exc:
                _raise_safe(exc, operation="read object metadata")
            value = {
                "Key": key,
                "Size": outcome.size_bytes,
                "ETag": head.get("ETag"),
                "LastModified": head.get("LastModified"),
                "StorageClass": head.get("StorageClass", "STANDARD"),
            }
            item = self._item(parsed, value, head)
            prior = priors.get(outcome.canonical_location)
            if (
                prior is not None
                and prior.provider_revision == item.provider_revision
                and prior.processing_config_hash == processing_config_hash
            ):
                artifacts.append(
                    S3Artifact(
                        item=item,
                        content=None,
                        content_hash=prior.content_hash,
                        fetched_at=self.clock(),
                        unchanged=True,
                    )
                )
            else:
                artifacts.append(self.fetch(parsed, item))
        return outcomes, artifacts
