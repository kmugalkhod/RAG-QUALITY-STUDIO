"""Durable encrypted raw-artifact storage with bounded plaintext materialization."""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.artifact_crypto import ArtifactEnvelope, ArtifactKeyring
from app.core.config import settings


@dataclass(frozen=True)
class StoredArtifact:
    storage_name: str
    path: Path
    state: str
    envelope: ArtifactEnvelope | None
    retained_until: datetime | None


def _durable_write(content: bytes) -> tuple[str, Path]:
    root = settings.storage_path
    root.mkdir(parents=True, exist_ok=True)
    name = uuid4().hex
    temporary = root / f"{name}.part"
    final = root / name
    with temporary.open("xb") as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, final)
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return name, final


def store(content: bytes, project_id: UUID, document_id: UUID) -> StoredArtifact:
    if not settings.artifact_encryption_enabled:
        name, path = _durable_write(content)
        return StoredArtifact(name, path, "legacy_plaintext", None, None)
    keyring = ArtifactKeyring.from_settings(settings)
    envelope = keyring.encrypt(content, project_id, document_id)
    name, path = _durable_write(envelope.ciphertext)
    return StoredArtifact(
        storage_name=name,
        path=path,
        state="encrypted",
        envelope=envelope,
        retained_until=datetime.now(timezone.utc)
        + timedelta(days=settings.artifact_retention_days),
    )


def model_values(stored: StoredArtifact) -> dict:
    envelope = stored.envelope
    return {
        "storage_name": stored.storage_name,
        "artifact_state": stored.state,
        "artifact_encryption_schema": envelope.schema_version if envelope else None,
        "artifact_key_version": envelope.key_version if envelope else None,
        "artifact_wrapped_key": envelope.wrapped_key if envelope else None,
        "artifact_wrap_nonce": envelope.wrap_nonce if envelope else None,
        "artifact_content_nonce": envelope.content_nonce if envelope else None,
        "raw_retained_until": stored.retained_until,
    }


def read(document) -> bytes:
    if document.artifact_state in {"deleting", "deleted"}:
        raise FileNotFoundError("The retained raw artifact has expired.")
    path = settings.storage_path / document.storage_name
    content = path.read_bytes()
    if document.artifact_state == "legacy_plaintext":
        return content
    keyring = ArtifactKeyring.from_settings(settings)
    return keyring.decrypt(
        ciphertext=content,
        wrapped_key=document.artifact_wrapped_key,
        wrap_nonce=document.artifact_wrap_nonce,
        content_nonce=document.artifact_content_nonce,
        key_version=document.artifact_key_version,
        schema_version=document.artifact_encryption_schema,
        project_id=document.project_id,
        document_id=document.id,
    )


@contextmanager
def temporary_plaintext(content: bytes):
    descriptor, name = tempfile.mkstemp(prefix="rag-artifact-", suffix=".tmp")
    path = Path(name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
        yield path
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


@contextmanager
def materialize(document):
    with temporary_plaintext(read(document)) as path:
        yield path


def rewrap(session: Session, document) -> dict:
    from app.models.document import Document

    current = session.scalar(
        select(Document).where(Document.id == document.id).with_for_update()
    )
    if current is None or current.artifact_state != "encrypted":
        raise FileNotFoundError("The retained raw artifact is unavailable.")
    keyring = ArtifactKeyring.from_settings(settings)
    wrapped_key, wrap_nonce, key_version = keyring.rewrap_artifact_key(
        wrapped_key=current.artifact_wrapped_key,
        wrap_nonce=current.artifact_wrap_nonce,
        key_version=current.artifact_key_version,
        schema_version=current.artifact_encryption_schema,
        project_id=current.project_id,
        document_id=current.id,
    )
    current.artifact_wrapped_key = wrapped_key
    current.artifact_wrap_nonce = wrap_nonce
    current.artifact_key_version = key_version
    session.commit()
    return {"status": "rewrapped", "key_version": key_version}


def cleanup_expired_raw_artifacts(db_engine, *, limit: int = 25) -> int:
    """Fenced, crash-recoverable deletion of expired encrypted raw bytes.

    Derived redacted content and immutable index/history rows are intentionally kept.
    Legacy plaintext is never deleted by this automatic policy.
    """

    from app.models.document import Document

    current = datetime.now(timezone.utc)
    claimed: list[tuple[UUID, str, UUID]] = []
    with Session(
        db_engine.execution_options(isolation_level="READ COMMITTED")
    ) as session:
        rows = session.scalars(
            select(Document)
            .where(
                Document.artifact_state.in_(["encrypted", "deleting"]),
                Document.raw_retained_until.is_not(None),
                Document.raw_retained_until <= current,
            )
            .order_by(Document.raw_retained_until, Document.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
        for row in rows:
            token = row.raw_deletion_token or uuid4()
            row.artifact_state = "deleting"
            row.raw_deletion_token = token
            row.raw_deletion_claimed_at = current
            claimed.append((row.id, row.storage_name, token))
        session.commit()

    completed = 0
    for document_id, storage_name, token in claimed:
        stored = settings.storage_path / storage_name
        staged = settings.storage_path / f"{storage_name}.retention-{token.hex}"
        try:
            if stored.exists():
                os.replace(stored, staged)
            with Session(
                db_engine.execution_options(isolation_level="READ COMMITTED")
            ) as session:
                row = session.scalar(
                    select(Document).where(Document.id == document_id).with_for_update()
                )
                if (
                    row is None
                    or row.artifact_state != "deleting"
                    or row.raw_deletion_token != token
                ):
                    if staged.exists() and not stored.exists():
                        os.replace(staged, stored)
                    continue
                row.artifact_state = "deleted"
                row.raw_deleted_at = datetime.now(timezone.utc)
                row.raw_deletion_token = None
                row.raw_deletion_claimed_at = None
                # Cryptographic erasure also makes protected extracted source text
                # and full pre-redaction diffs unrecoverable after retention expiry.
                row.artifact_encryption_schema = None
                row.artifact_key_version = None
                row.artifact_wrapped_key = None
                row.artifact_wrap_nonce = None
                row.artifact_content_nonce = None
                session.commit()
            staged.unlink(missing_ok=True)
            completed += 1
        except OSError:
            if staged.exists() and not stored.exists():
                try:
                    os.replace(staged, stored)
                except OSError:
                    pass
            with Session(
                db_engine.execution_options(isolation_level="READ COMMITTED")
            ) as session:
                row = session.scalar(
                    select(Document).where(Document.id == document_id).with_for_update()
                )
                if (
                    row is not None
                    and row.artifact_state == "deleting"
                    and row.raw_deletion_token == token
                ):
                    row.artifact_state = "encrypted"
                    row.raw_deletion_token = None
                    row.raw_deletion_claimed_at = None
                    session.commit()
    return completed
