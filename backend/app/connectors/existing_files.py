"""Project-scoped adapter over uploaded immutable files."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import (
    ChangedFetch,
    ConnectionCheck,
    ConnectorFailure,
    ConnectorIssue,
    DiscoveredItem,
    DiscoveryPage,
)
from app.models.document import Document
from app.schemas.ingestion import ExistingFilesConfig


class ExistingFilesConnector:
    kind = "existing_files"
    config_version = "1"
    page_size = 100

    def __init__(self, session: Session, project_id: UUID):
        self.session = session
        self.project_id = project_id

    def validate(self, config: object, connection: object | None) -> None:
        if connection is not None:
            raise ConnectorFailure(
                ConnectorIssue(
                    code="connection_not_supported",
                    message="Existing project files do not use a source connection.",
                    retryable=False,
                )
            )
        parsed = ExistingFilesConfig.model_validate(config)
        found = set(
            self.session.scalars(
                select(Document.id).where(
                    Document.project_id == self.project_id,
                    Document.origin_kind == "upload",
                    Document.id.in_(parsed.document_ids),
                )
            )
        )
        if found != set(parsed.document_ids):
            raise ConnectorFailure(
                ConnectorIssue(
                    code="document_not_found",
                    message="One or more selected files were not found in this project.",
                    retryable=False,
                )
            )

    def test_connection(self, connection: object | None) -> ConnectionCheck:
        if connection is not None:
            return ConnectionCheck(
                status="unavailable",
                message="Existing project files do not use a source connection.",
            )
        return ConnectionCheck(
            status="available", message="Project files are available."
        )

    def discover(self, config: object, cursor: str | None = None) -> DiscoveryPage:
        parsed = ExistingFilesConfig.model_validate(config)
        self.validate(parsed, None)
        try:
            offset = int(cursor or "0")
        except ValueError as exc:
            raise ConnectorFailure(
                ConnectorIssue(
                    code="invalid_cursor",
                    message="The file discovery cursor is invalid.",
                    retryable=False,
                )
            ) from exc
        if offset < 0 or offset > len(parsed.document_ids):
            raise ConnectorFailure(
                ConnectorIssue(
                    code="invalid_cursor",
                    message="The file discovery cursor is invalid.",
                    retryable=False,
                )
            )
        selected = parsed.document_ids[offset : offset + self.page_size]
        documents = {
            document.id: document
            for document in self.session.scalars(
                select(Document).where(
                    Document.project_id == self.project_id,
                    Document.origin_kind == "upload",
                    Document.id.in_(selected),
                )
            )
        }
        items = tuple(self._item(documents[document_id]) for document_id in selected)
        next_offset = offset + len(selected)
        return DiscoveryPage(
            items=items,
            next_cursor=str(next_offset)
            if next_offset < len(parsed.document_ids)
            else None,
        )

    def fetch(self, item: DiscoveredItem, prior_revision: object | None = None):
        try:
            document_id = UUID(item.external_id)
        except ValueError as exc:
            raise ConnectorFailure(
                ConnectorIssue(
                    code="invalid_document_identity",
                    message="The selected file identity is invalid.",
                    retryable=False,
                )
            ) from exc
        document = self.session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.project_id == self.project_id,
                Document.origin_kind == "upload",
            )
        )
        if document is None:
            raise ConnectorFailure(
                ConnectorIssue(
                    code="document_not_found",
                    message="The selected file is no longer available in this project.",
                    retryable=False,
                )
            )
        return ChangedFetch(
            status="changed",
            item=self._item(document),
            content_hash=document.content_hash,
            stored_object_ref=document.storage_name,
            fetched_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _item(document: Document) -> DiscoveredItem:
        return DiscoveredItem(
            external_id=str(document.id),
            display_name=document.filename,
            canonical_location=f"project-file:{document.id}",
            media_type=document.media_type,
            provider_revision=document.content_hash,
            modified_at=document.created_at,
            metadata={"size_bytes": document.size_bytes},
        )
