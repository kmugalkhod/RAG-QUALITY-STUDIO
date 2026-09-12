from copy import deepcopy
import pytest
from pydantic import TypeAdapter, ValidationError

from app.connectors.base import (
    ConnectorFailure,
    ConnectorIssue,
    FailedFetch,
    FetchResult,
    SourceConnector,
)
from app.schemas.ingestion import IngestionPipelineSave
from connector_fixtures import DeterministicConnector


def ingestion_draft(*, source_count=1):
    source_nodes = [
        {
            "id": f"source-{number}",
            "type": "source",
            "config": {
                "kind": "website",
                "selection": {
                    "mode": "single_url",
                    "url": f"https://example.com/{number}",
                },
                "allowed_origins": ["https://example.com"],
                "max_pages": 10,
                "max_depth": 2,
                "max_response_bytes": 1_000_000,
                "max_total_bytes": 5_000_000,
                "request_timeout_seconds": 10,
                "deadline_seconds": 120,
                "concurrency": 2,
                "requests_per_second": 2,
                "redirect_limit": 3,
                "user_agent": "RAG-Quality-Studio/1",
            },
        }
        for number in range(source_count)
    ]
    processing = [
        {"id": "extract", "type": "extract"},
        {"id": "clean", "type": "clean"},
        {"id": "chunk", "type": "chunk", "size": 1000, "overlap": 100},
        {
            "id": "embed",
            "type": "embed",
            "provider": "openrouter",
            "model": "openai/text-embedding-3-small",
            "dimensions": 1536,
            "config_version": "1",
        },
        {
            "id": "publish",
            "type": "publish_index",
            "knowledge_set_name": "Product docs",
        },
    ]
    nodes = source_nodes + processing
    edges = [{"source": node["id"], "target": "extract"} for node in source_nodes] + [
        {"source": "extract", "target": "clean"},
        {"source": "clean", "target": "chunk"},
        {"source": "chunk", "target": "embed"},
        {"source": "embed", "target": "publish"},
    ]
    return {
        "kind": "ingestion",
        "name": "Website ingestion",
        "execution": {"schema_version": 1, "nodes": nodes, "edges": edges},
        "layout": {
            "positions": {
                node["id"]: {"x": number * 100, "y": number * 120}
                for number, node in enumerate(nodes)
            }
        },
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda draft: draft["execution"]["nodes"].append(
            deepcopy(draft["execution"]["nodes"][0])
        ),
        lambda draft: draft["execution"]["edges"].append(
            {"source": "publish", "target": "extract"}
        ),
        lambda draft: draft["execution"]["edges"].pop(),
        lambda draft: draft["execution"]["nodes"][0].update(type="script"),
        lambda draft: draft["execution"]["nodes"][0]["config"].update(kind="unknown"),
        lambda draft: draft["execution"]["nodes"][0]["config"].update(secret="x"),
        lambda draft: draft["execution"]["nodes"][3].update(overlap=1000),
        lambda draft: draft["layout"]["positions"].pop("publish"),
        lambda draft: draft.update(unknown=True),
    ],
)
def test_strict_ingestion_graph_rejects_invalid_configuration(mutate):
    value = ingestion_draft()
    mutate(value)
    with pytest.raises(ValidationError):
        IngestionPipelineSave.model_validate(value)


def test_ingestion_graph_accepts_one_to_ten_sources_only():
    assert (
        len(
            IngestionPipelineSave.model_validate(
                ingestion_draft(source_count=10)
            ).execution.nodes
        )
        == 15
    )
    with pytest.raises(ValidationError):
        IngestionPipelineSave.model_validate(ingestion_draft(source_count=11))


def test_deterministic_connector_contract_supports_changed_and_unchanged():
    connector = DeterministicConnector({"b": b"two", "a": b"one"})
    assert isinstance(connector, SourceConnector)
    first_page = connector.discover({"scope": "all"})
    second_page = connector.discover({"scope": "all"})
    assert first_page == second_page
    assert [item.external_id for item in first_page.items] == ["a", "b"]
    changed = connector.fetch(first_page.items[0])
    unchanged = connector.fetch(first_page.items[0], changed.content_hash)
    adapter = TypeAdapter(FetchResult)
    assert adapter.validate_python(changed).status == "changed"
    assert adapter.validate_python(unchanged).status == "unchanged"


def test_connector_errors_are_sanitized_and_retry_classified():
    issue = ConnectorIssue(
        code="rate_limited",
        message="Provider is temporarily unavailable.",
        retryable=True,
        retry_after_seconds=2,
    )
    error = ConnectorFailure(issue)
    assert str(error) == "Provider is temporarily unavailable."
    assert error.issue.retryable is True
    item = DeterministicConnector({"one": b"value"}).discover({"scope": "all"}).items[0]
    result = TypeAdapter(FetchResult).validate_python(
        FailedFetch(status="failed", item=item, error=issue)
    )
    assert result.error.code == "rate_limited"
