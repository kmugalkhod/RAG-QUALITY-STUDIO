from uuid import UUID, uuid4
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal, current_principal
from app.core.config import settings
from app.db.session import get_session, get_deployment_session
from app.main import app
from app.models.deployment import AnswerDeployment, AnswerDeploymentRelease
from app.models.index import IndexVersion, KnowledgeSet
from app.models.pipeline import Pipeline, PipelineVersion
from app.models.project import Project
from app.models.security import ProjectMembership, UserIdentity
from app.providers import embeddings
from app.schemas.pipeline import DEFAULT_TEMPLATE


@pytest.fixture
def management_api(database, monkeypatch):
    engine, _ = database
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr("test-only"))
    monkeypatch.setattr(settings, "chat_model", "test/chat")
    monkeypatch.setattr(settings, "embedding_dimensions", 3)
    monkeypatch.setattr(settings, "deployment_pricing_version", "test-1")
    monkeypatch.setattr(
        settings,
        "deployment_approved_prices",
        {
            "test/chat": {"input_per_million_usd": 1, "output_per_million_usd": 2},
            settings.embedding_model: {"input_per_million_usd": 1},
        },
    )
    config = embeddings.configured().model_dump()
    with engine.connect() as connection:
        outer = connection.begin()
        with Session(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        ) as setup:
            p = Project(name="Owned", organization_id="org_a")
            q = Project(name="Foreign", organization_id="org_b")
            setup.add_all([p, q])
            setup.flush()
            user = UserIdentity(external_subject=f"user_{uuid4()}")
            editor = UserIdentity(external_subject=f"user_{uuid4()}")
            viewer = UserIdentity(external_subject=f"user_{uuid4()}")
            setup.add_all([user, editor, viewer])
            setup.flush()
            setup.add_all(
                [
                    ProjectMembership(project_id=p.id, user_id=user.id, role="owner"),
                    ProjectMembership(
                        project_id=p.id, user_id=editor.id, role="editor"
                    ),
                    ProjectMembership(
                        project_id=p.id, user_id=viewer.id, role="viewer"
                    ),
                ]
            )
            pipe = Pipeline(project_id=p.id, name="Saved answer", kind="answer")
            knowledge = KnowledgeSet(project_id=p.id, name="Knowledge")
            setup.add_all([pipe, knowledge])
            setup.flush()
            index = IndexVersion(
                project_id=p.id,
                knowledge_set_id=knowledge.id,
                version=1,
                dimensions=3,
                embedding_config=config,
                status="succeeded",
                chunk_count=1,
                embedded_count=1,
                attempts=0,
                failures=0,
            )
            setup.add(index)
            setup.flush()
            kinds = ("question", "retriever", "prompt", "llm", "answer")
            execution = {
                "schema_version": 1,
                "nodes": [
                    {"id": "question", "type": "question"},
                    {
                        "id": "retriever",
                        "type": "retriever",
                        "index_id": str(index.id),
                        "top_k": 1,
                    },
                    {"id": "prompt", "type": "prompt", "template": DEFAULT_TEMPLATE},
                    {
                        "id": "llm",
                        "type": "llm",
                        "model": "test/chat",
                        "max_tokens": 512,
                        "temperature": 0,
                    },
                    {"id": "answer", "type": "answer"},
                ],
                "edges": [{"source": a, "target": b} for a, b in zip(kinds, kinds[1:])],
            }
            version = PipelineVersion(
                project_id=p.id,
                pipeline_id=pipe.id,
                version=1,
                name="Saved answer",
                execution=execution,
                layout={},
            )
            setup.add(version)
            setup.commit()

        test_session = Session(
            bind=connection, join_transaction_mode="create_savepoint"
        )

        def override_session():
            yield test_session

        def principal(identity, role, org="org_a"):
            return Principal(
                identity.id, identity.external_subject, None, "clerk", org, "org:member"
            )

        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_deployment_session] = override_session
        app.dependency_overrides[current_principal] = lambda: principal(user, "owner")
        try:
            with TestClient(app) as client:
                yield (
                    client,
                    connection,
                    p,
                    q,
                    pipe,
                    version,
                    index,
                    (user, editor, viewer),
                    principal,
                )
        finally:
            app.dependency_overrides.clear()
            test_session.close()
            outer.rollback()


def test_release_lifecycle_roles_and_pinning(management_api):
    client, connection, p, q, pipe, version, index, identities, principal = (
        management_api
    )
    base = f"/api/projects/{p.id}/answer-deployments"
    payload = {
        "name": "Support",
        "pipeline_id": str(pipe.id),
        "pipeline_version_id": str(version.id),
        "index_id": str(index.id),
    }
    created = client.post(base, json=payload)
    assert created.status_code == 201, created.text
    deployment = created.json()
    release = deployment["releases"][0]
    assert deployment["state"] == "paused" and deployment["active_release_id"] is None
    assert client.get(base).json()["total"] == 1
    assert client.get(base.replace(str(p.id), str(q.id))).status_code == 404
    app.dependency_overrides[current_principal] = lambda: principal(
        identities[0], "owner", "org_b"
    )
    assert client.get(base).status_code == 404
    app.dependency_overrides[current_principal] = lambda: principal(
        identities[0], "owner"
    )
    assert (
        client.post(base, json={**payload, "index_id": str(uuid4())}).status_code == 409
    )
    with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
        different_index = IndexVersion(
            project_id=p.id,
            knowledge_set_id=index.knowledge_set_id,
            version=2,
            dimensions=3,
            embedding_config=index.embedding_config,
            status="succeeded",
            chunk_count=1,
            embedded_count=1,
            attempts=0,
            failures=0,
        )
        session.add(different_index)
        session.flush()
        different_id = different_index.id
        session.commit()
    assert (
        client.post(
            f"{base}/{deployment['id']}/releases",
            json={
                "pipeline_version_id": str(version.id),
                "index_id": str(different_id),
            },
        ).status_code
        == 409
    )
    path = f"{base}/{deployment['id']}"
    promoted = client.post(
        path + "/promotions",
        headers={"If-Match": '"1"'},
        json={"release_id": release["id"], "reason": "Reviewed"},
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["active_release_id"] == release["id"]
    changed = client.put(
        path + "/limits",
        headers={"If-Match": '"2"'},
        json={
            "rate_per_minute": 5,
            "concurrent_runs": 1,
            "queued_runs": 2,
            "daily_budget_usd": "1.00",
            "monthly_budget_usd": "2.00",
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["limits"]["rate_per_minute"] == 5
    assert client.get(path + "/events").json()["total"] == 3
    assert client.post(path + "/pause", headers={"If-Match": '"2"'}).status_code == 412
    paused = client.post(path + "/pause", headers={"If-Match": '"3"'})
    assert paused.status_code == 200 and paused.json()["state"] == "paused"
    app.dependency_overrides[current_principal] = lambda: principal(
        identities[1], "editor"
    )
    assert client.get(path).status_code == 200
    assert client.post(path + "/resume", headers={"If-Match": '"4"'}).status_code == 403
    app.dependency_overrides[current_principal] = lambda: principal(
        identities[2], "viewer"
    )
    assert client.get(path).status_code == 200
    assert client.post(path + "/pause", headers={"If-Match": '"4"'}).status_code == 403
    app.dependency_overrides[current_principal] = lambda: principal(
        identities[0], "owner"
    )
    archived = client.post(
        path + "/archive",
        headers={"If-Match": '"4"'},
        json={"reason": "Retired"},
    )
    assert archived.status_code == 200 and archived.json()["state"] == "archived"
    assert client.post(path + "/resume", headers={"If-Match": '"5"'}).status_code == 409
    with Session(bind=connection) as session:
        row = session.scalar(
            select(AnswerDeployment).where(AnswerDeployment.id == deployment["id"])
        )
        saved = session.scalar(
            select(AnswerDeploymentRelease).where(
                AnswerDeploymentRelease.id == release["id"]
            )
        )
        assert row.active_release_id == saved.id
        assert saved.pipeline_version_id == version.id and saved.index_id == index.id


def test_one_time_key_rotation_revocation_and_scope(management_api, monkeypatch):
    client, _, p, _, pipe, version, index, identities, principal = management_api
    monkeypatch.setattr(settings, "deployed_answers_enabled", True)
    monkeypatch.setattr(settings, "deployment_local_keys_enabled", True)
    monkeypatch.setattr(settings, "deployment_active_pepper", "test-v1")
    monkeypatch.setattr(
        settings,
        "deployment_key_peppers",
        {"test-v1": SecretStr("only-for-tests-32-byte-pepper-value")},
    )
    base = f"/api/projects/{p.id}/answer-deployments"
    created = client.post(
        base,
        json={
            "name": "Support",
            "pipeline_id": str(pipe.id),
            "pipeline_version_id": str(version.id),
            "index_id": str(index.id),
        },
    ).json()
    path = f"{base}/{created['id']}"
    key_response = client.post(
        path + "/keys",
        json={"label": "Customer"},
        headers={"Idempotency-Key": "issue-once"},
    )
    assert key_response.status_code == 201, key_response.text
    key = key_response.json()
    assert key_response.headers["Cache-Control"] == "no-store"
    assert key["secret"].startswith(key["prefix"] + "_")
    listed = client.get(path + "/keys").json()
    assert key["secret"] not in str(listed)
    replay = client.post(
        path + "/keys",
        json={"label": "Customer"},
        headers={"Idempotency-Key": "issue-once"},
    )
    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == "key_secret_already_issued"
    assert replay.json()["error"]["details"][0]["key_id"] == key["id"]
    assert key["secret"] not in replay.text
    status = f"/v1/answer-deployments/{created['id']}/status"
    bearer = {"Authorization": f"Bearer {key['secret']}"}
    assert client.get(status, headers=bearer).status_code == 200
    assert (
        client.get(
            status, headers={**bearer, "Origin": "http://127.0.0.1:5273"}
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/v1/answer-deployments/{uuid4()}/status", headers=bearer
        ).status_code
        == 404
    )
    assert (
        client.get(
            status, headers={"Authorization": "Bearer " + key["secret"][:-1] + "x"}
        ).status_code
        == 401
    )
    rotated = client.post(path + f"/keys/{key['id']}/rotate")
    assert rotated.status_code == 201, rotated.text
    next_key = rotated.json()
    assert next_key["client_id"] == key["client_id"]
    assert next_key["secret"] != key["secret"]
    assert (
        client.get(
            status, headers={"Authorization": f"Bearer {next_key['secret']}"}
        ).status_code
        == 200
    )
    assert client.post(path + f"/keys/{next_key['id']}/revoke").status_code == 200
    assert (
        client.get(
            status, headers={"Authorization": f"Bearer {next_key['secret']}"}
        ).status_code
        == 401
    )
    app.dependency_overrides[current_principal] = lambda: principal(
        identities[1], "editor"
    )
    assert client.get(path + "/keys").status_code == 403
    assert client.post(path + "/keys", json={"label": "No"}).status_code == 403


def test_atomic_admission_replay_and_budget(management_api, monkeypatch):
    from unittest.mock import patch
    from app.providers import generation

    client, connection, p, _, pipe, version, index, _, _ = management_api
    monkeypatch.setattr(settings, "deployed_answers_enabled", True)
    monkeypatch.setattr(settings, "deployment_local_keys_enabled", True)
    monkeypatch.setattr(settings, "deployment_active_pepper", "test-v1")
    monkeypatch.setattr(
        settings,
        "deployment_key_peppers",
        {"test-v1": SecretStr("only-for-tests-32-byte-pepper-value")},
    )
    monkeypatch.setattr(settings, "deployment_pricing_version", "test-1")
    monkeypatch.setattr(
        settings,
        "deployment_approved_prices",
        {
            "test/chat": {
                "input_per_million_usd": 1,
                "output_per_million_usd": 2,
            },
            settings.embedding_model: {"input_per_million_usd": 1},
        },
    )
    monkeypatch.setattr(settings, "deployment_org_daily_usd", Decimal("0.01"))
    base = f"/api/projects/{p.id}/answer-deployments"
    created = client.post(
        base,
        json={
            "name": "Support",
            "pipeline_id": str(pipe.id),
            "pipeline_version_id": str(version.id),
            "index_id": str(index.id),
        },
    ).json()
    path = f"{base}/{created['id']}"
    release_id = created["releases"][0]["id"]
    assert (
        client.post(
            path + "/promotions",
            headers={"If-Match": '"1"'},
            json={"release_id": release_id, "reason": "Reviewed"},
        ).status_code
        == 200
    )
    key = client.post(path + "/keys", json={"label": "Customer"}).json()["secret"]
    question_path = f"/v1/answer-deployments/{created['id']}/questions"
    headers = {"Authorization": f"Bearer {key}", "Idempotency-Key": "order-1"}
    with patch.object(generation.OpenRouterChat, "generate") as provider:
        assert (
            client.post(
                question_path,
                headers={"Authorization": f"Bearer {key}"},
                json={"question": "What?"},
            ).status_code
            == 428
        )
        first = client.post(question_path, headers=headers, json={"question": "What?"})
        assert first.status_code == 202, first.text
        replay = client.post(question_path, headers=headers, json={"question": "What?"})
        assert replay.status_code == 200
        assert replay.json()["id"] == first.json()["id"]
        assert (
            client.post(
                question_path, headers=headers, json={"question": "Different?"}
            ).status_code
            == 409
        )
        denied = client.post(
            question_path,
            headers={**headers, "Idempotency-Key": "order-2"},
            json={"question": "Again?"},
        )
        assert denied.status_code == 402, denied.text
        provider.assert_not_called()
    status_url = first.json()["status_url"]
    assert (
        client.get(status_url, headers={"Authorization": f"Bearer {key}"}).json()[
            "status"
        ]
        == "queued"
    )
    with Session(bind=connection) as session:
        from app.models.deployment import DeployedAnswerRun, DeploymentUsageEntry

        assert session.query(DeployedAnswerRun).count() == 1
        assert session.query(DeploymentUsageEntry).count() == 1


def test_fenced_worker_result_and_duplicate_delivery(management_api, monkeypatch):
    from unittest.mock import patch
    from app.providers import generation
    from app.workers.deployed_answers import process_deployed

    client, connection, p, _, pipe, version, index, _, _ = management_api
    monkeypatch.setattr(settings, "deployed_answers_enabled", True)
    monkeypatch.setattr(settings, "deployment_local_keys_enabled", True)
    monkeypatch.setattr(settings, "deployment_active_pepper", "test-v1")
    monkeypatch.setattr(
        settings,
        "deployment_key_peppers",
        {"test-v1": SecretStr("only-for-tests-32-byte-pepper-value")},
    )
    monkeypatch.setattr(settings, "deployment_pricing_version", "test-1")
    monkeypatch.setattr(
        settings,
        "deployment_approved_prices",
        {
            "test/chat": {"input_per_million_usd": 1, "output_per_million_usd": 2},
            settings.embedding_model: {"input_per_million_usd": 1},
        },
    )
    base = f"/api/projects/{p.id}/answer-deployments"
    created = client.post(
        base,
        json={
            "name": "Support",
            "pipeline_id": str(pipe.id),
            "pipeline_version_id": str(version.id),
            "index_id": str(index.id),
        },
    ).json()
    path = f"{base}/{created['id']}"
    release_id = created["releases"][0]["id"]
    assert (
        client.post(
            path + "/promotions",
            headers={"If-Match": '"1"'},
            json={"release_id": release_id, "reason": "Reviewed"},
        ).status_code
        == 200
    )
    key = client.post(path + "/keys", json={"label": "Customer"}).json()["secret"]
    headers = {"Authorization": f"Bearer {key}", "Idempotency-Key": "order-1"}
    accepted = client.post(
        f"/v1/answer-deployments/{created['id']}/questions",
        headers=headers,
        json={"question": "What?"},
    )
    assert accepted.status_code == 202, accepted.text
    evidence = {
        "document_id": str(uuid4()),
        "filename": "Policy",
        "page_number": 2,
        "rank": 1,
        "text": "Returns take 30 days.",
    }
    with (
        patch("app.services.indexes.retrieve", return_value={"items": [evidence]}),
        patch.object(
            generation.OpenRouterChat,
            "generate",
            return_value=generation.Completion(
                "Returns take 30 days. [S1]",
                "test/chat",
                {"total_tokens": 20},
                None,
            ),
        ) as provider,
    ):
        process_deployed(accepted.json()["id"], connection)
        process_deployed(accepted.json()["id"], connection)
        assert provider.call_count == 1
    result = client.get(
        accepted.json()["result_url"], headers={"Authorization": f"Bearer {key}"}
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["status"] == "succeeded"
    assert body["citations"][0]["excerpt"] == "Returns take 30 days."
    assert body["cost_usd"] is None
    failed = client.post(
        f"/v1/answer-deployments/{created['id']}/questions",
        headers={**headers, "Idempotency-Key": "provider-failure"},
        json={"question": "And now?"},
    )
    assert failed.status_code == 202
    with (
        patch("app.services.indexes.retrieve", return_value={"items": [evidence]}),
        patch.object(
            generation.OpenRouterChat,
            "generate",
            side_effect=RuntimeError("provider body secret"),
        ) as provider,
    ):
        process_deployed(failed.json()["id"], connection)
        process_deployed(failed.json()["id"], connection)
        assert provider.call_count == 1
    failure_result = client.get(
        failed.json()["result_url"], headers={"Authorization": f"Bearer {key}"}
    )
    assert failure_result.json()["error_code"] == "provider_outcome_unknown"
    assert "provider body secret" not in failure_result.text
    from datetime import datetime, timedelta, timezone
    from app.models.deployment import DeployedAnswerRun
    from app.workers.deployed_answers import _session
    from app.workers.dispatcher import redact_expired_deployed_once

    with _session(connection) as session:
        row = session.get(DeployedAnswerRun, UUID(accepted.json()["id"]))
        row.result_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    assert redact_expired_deployed_once(connection) == 1
    assert (
        client.get(
            accepted.json()["result_url"], headers={"Authorization": f"Bearer {key}"}
        ).status_code
        == 410
    )
    with _session(connection) as session:
        row = session.get(DeployedAnswerRun, UUID(accepted.json()["id"]))
        assert row.question is None and row.answer is None and row.evidence is None


def test_worker_recovery_before_and_after_paid_marker_and_cancel(
    management_api, monkeypatch
):
    from datetime import datetime, timedelta, timezone
    from app.models.deployment import DeployedAnswerRun, DeploymentUsageEntry
    from app.workers.deployed_answers import (
        claim,
        _before_call,
        _checkpoint,
        _session,
        Fenced,
    )
    from app.workers.dispatcher import dispatch_deployed_once

    client, connection, p, _, pipe, version, index, _, _ = management_api
    monkeypatch.setattr(settings, "deployed_answers_enabled", True)
    monkeypatch.setattr(settings, "deployment_local_keys_enabled", True)
    monkeypatch.setattr(settings, "deployment_active_pepper", "test-v1")
    monkeypatch.setattr(
        settings,
        "deployment_key_peppers",
        {"test-v1": SecretStr("only-for-tests-32-byte-pepper-value")},
    )
    base = f"/api/projects/{p.id}/answer-deployments"
    created = client.post(
        base,
        json={
            "name": "Support",
            "pipeline_id": str(pipe.id),
            "pipeline_version_id": str(version.id),
            "index_id": str(index.id),
        },
    ).json()
    path = f"{base}/{created['id']}"
    assert (
        client.post(
            path + "/promotions",
            headers={"If-Match": '"1"'},
            json={"release_id": created["releases"][0]["id"], "reason": "Reviewed"},
        ).status_code
        == 200
    )
    secret = client.post(path + "/keys", json={"label": "Customer"}).json()["secret"]
    question_path = f"/v1/answer-deployments/{created['id']}/questions"

    def admit(idempotency):
        response = client.post(
            question_path,
            headers={
                "Authorization": f"Bearer {secret}",
                "Idempotency-Key": idempotency,
            },
            json={"question": "What?"},
        )
        assert response.status_code == 202, response.text
        return response.json()["id"]

    ambiguous = admit("ambiguous")
    token = claim(UUID(ambiguous), connection)
    with _session(connection) as session:
        _before_call(session, UUID(ambiguous), token, "embedding_call")
    with _session(connection) as session:
        row = session.get(DeployedAnswerRun, UUID(ambiguous))
        row.deadline_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    sent = []
    dispatch_deployed_once(connection, send=sent.append)
    with _session(connection) as session:
        row = session.get(DeployedAnswerRun, UUID(ambiguous))
        assert row.status == "failed" and row.error_code == "provider_outcome_unknown"
        assert (
            session.query(DeploymentUsageEntry)
            .filter_by(run_id=row.id, entry_type="release")
            .count()
            == 0
        )
    assert sent == []

    safe = admit("before-provider")
    assert claim(UUID(safe), connection)
    with _session(connection) as session:
        row = session.get(DeployedAnswerRun, UUID(safe))
        row.deadline_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    dispatch_deployed_once(connection, send=sent.append)
    with _session(connection) as session:
        assert session.get(DeployedAnswerRun, UUID(safe)).status == "queued"
    assert UUID(safe) in sent

    redis_down = admit("redis-down")
    with pytest.raises(RuntimeError, match="Redis unavailable"):
        dispatch_deployed_once(
            connection,
            send=lambda run_id: (_ for _ in ()).throw(
                RuntimeError("Redis unavailable")
            ),
        )
    with _session(connection) as session:
        row = session.get(DeployedAnswerRun, UUID(redis_down))
        assert row.status == "queued" and row.dispatched_at is None

    paid_cancel = admit("paid-cancel")
    paid_token = claim(UUID(paid_cancel), connection)
    with _session(connection) as session:
        _before_call(session, UUID(paid_cancel), paid_token, "embedding_call")
    response = client.post(path + f"/runs/{paid_cancel}/cancel")
    assert (
        response.status_code == 200 and response.json()["status"] == "cancel_requested"
    )
    with _session(connection) as session, pytest.raises(Fenced):
        _checkpoint(session, UUID(paid_cancel), paid_token, {"evidence": []})
    with _session(connection) as session:
        row = session.get(DeployedAnswerRun, UUID(paid_cancel))
        assert row.status == "cancelled"
        assert (
            session.query(DeploymentUsageEntry)
            .filter_by(run_id=row.id, entry_type="release")
            .count()
            == 0
        )

    cancelled = admit("cancel")
    response = client.post(path + f"/runs/{cancelled}/cancel")
    assert response.status_code == 200 and response.json()["status"] == "cancelled"
    with _session(connection) as session:
        assert (
            session.query(DeploymentUsageEntry)
            .filter_by(run_id=UUID(cancelled), entry_type="release")
            .count()
            == 1
        )
