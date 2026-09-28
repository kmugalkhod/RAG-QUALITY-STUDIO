"""Private widget contract on isolated PostgreSQL and the existing admission path."""
# ruff: noqa: F811

from datetime import datetime, timedelta, timezone

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.deployment import DeployedAnswerRun, WidgetToken
from test_deployment_management import management_api  # noqa: F401


def setup_widget(management_api, monkeypatch):
    client, connection, project, _, pipe, version, index, _, _ = management_api
    monkeypatch.setattr(settings, "deployed_answers_enabled", True)
    monkeypatch.setattr(settings, "deployment_local_keys_enabled", True)
    monkeypatch.setattr(settings, "deployment_active_pepper", "test-v1")
    monkeypatch.setattr(
        settings,
        "deployment_key_peppers",
        {"test-v1": SecretStr("only-for-tests-32-byte-pepper-value")},
    )
    monkeypatch.setattr(settings, "widget_enabled", True)
    monkeypatch.setattr(
        settings,
        "widget_token_hash_key",
        SecretStr("separate-widget-token-hash-key-for-tests-1234"),
    )
    monkeypatch.setattr(settings, "widget_frame_origin", "http://127.0.0.1:5274")
    base = f"/api/projects/{project.id}/answer-deployments"
    created = client.post(
        base,
        json={
            "name": "Widget",
            "pipeline_id": str(pipe.id),
            "pipeline_version_id": str(version.id),
            "index_id": str(index.id),
        },
    )
    assert created.status_code == 201, created.text
    deployment = created.json()
    path = f"{base}/{deployment['id']}"
    promoted = client.post(
        path + "/promotions",
        headers={"If-Match": '"1"'},
        json={"release_id": deployment["releases"][0]["id"], "reason": "test"},
    )
    assert promoted.status_code == 200, promoted.text
    saved = client.put(
        path + "/widget",
        headers={"If-Match": '"2"'},
        json={
            "enabled": True,
            "allowed_origins": ["http://127.0.0.1:5275"],
            "branding": {
                "title": "Support",
                "greeting": "Ask us",
                "color": "blue",
                "position": "right",
            },
        },
    )
    assert saved.status_code == 200, saved.text
    key = client.post(path + "/keys", json={"label": "customer server"})
    assert key.status_code == 201, key.text
    public = f"/v1/answer-deployments/{deployment['id']}"
    return client, connection, path, public, key.json()


def exchange(client, public, key, visitor="a" * 40, origin="http://127.0.0.1:5275"):
    return client.post(
        public + "/widget-tokens",
        headers={"Authorization": f"Bearer {key['secret']}"},
        json={"visitor_session_id": visitor, "site_origin": origin},
    )


def test_public_static_embed_tokens_and_disable(management_api, monkeypatch):
    client, _, path, public, private_key = setup_widget(management_api, monkeypatch)
    endpoint = public + "/widget/public-token"
    payload = {"visitor_session_id": "a" * 40, "site_origin": "http://127.0.0.1:5275"}
    frame = {"Origin": "http://127.0.0.1:5274"}
    assert client.get(public + "/widget/config").json()["public_enabled"] is False
    assert client.post(endpoint, headers=frame, json=payload).status_code == 403
    assert (
        client.post(
            endpoint, headers={"Origin": "http://127.0.0.1:5275"}, json=payload
        ).status_code
        == 403
    )

    saved = client.put(
        path + "/widget",
        headers={"If-Match": '"3"'},
        json={
            "enabled": True,
            "public_enabled": True,
            "allowed_origins": ["http://127.0.0.1:5275"],
            "branding": {
                "title": "Support",
                "greeting": "Ask us",
                "color": "blue",
                "position": "right",
            },
        },
    )
    assert saved.status_code == 200, saved.text
    assert client.get(public + "/widget/config").json()["public_enabled"] is True
    keys = client.get(path + "/keys").json()["items"]
    assert len(keys) == 1 and keys[0]["id"] == private_key["id"]
    assert (
        client.post(
            endpoint,
            headers=frame,
            json={**payload, "site_origin": "http://127.0.0.1:5276"},
        ).status_code
        == 403
    )
    issued = client.post(endpoint, headers=frame, json=payload)
    assert issued.status_code == 201, issued.text
    token = issued.json()["token"]
    other = client.post(
        endpoint, headers=frame, json={**payload, "visitor_session_id": "b" * 40}
    ).json()["token"]
    monkeypatch.setattr(settings, "widget_exchange_rpm", 2)
    assert client.post(endpoint, headers=frame, json=payload).status_code == 429
    browser = {
        **frame,
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": "public-1",
    }
    asked = client.post(
        public + "/widget/questions",
        headers=browser,
        json={"question": "What is the answer?"},
    )
    assert asked.status_code == 202, asked.text
    assert (
        client.get(
            asked.json()["status_url"],
            headers={**frame, "Authorization": f"Bearer {other}"},
        ).status_code
        == 404
    )

    disabled = client.put(
        path + "/widget",
        headers={"If-Match": '"4"'},
        json={
            "enabled": True,
            "public_enabled": False,
            "allowed_origins": ["http://127.0.0.1:5275"],
            "branding": {
                "title": "Support",
                "greeting": "Ask us",
                "color": "blue",
                "position": "right",
            },
        },
    )
    assert disabled.status_code == 200, disabled.text
    assert client.post(endpoint, headers=frame, json=payload).status_code == 403
    assert client.get(public + "/widget/status", headers=browser).status_code == 403
    assert exchange(client, public, private_key).status_code == 201


def test_exchange_copied_script_origins_and_management_isolation(
    management_api, monkeypatch
):
    client, _, path, public, key = setup_widget(management_api, monkeypatch)
    config = client.get(public + "/widget/config")
    assert config.status_code == 200
    assert "secret" not in config.text and "organization_id" not in config.text
    assert (
        client.post(
            public + "/widget-tokens",
            json={
                "visitor_session_id": "a" * 40,
                "site_origin": "http://127.0.0.1:5275",
            },
        ).status_code
        == 401
    )
    assert (
        exchange(client, public, key, origin="http://127.0.0.1:5276").status_code == 403
    )
    assert (
        exchange(
            client, public, key, origin="https://example.com.evil.test"
        ).status_code
        == 403
    )
    assert (
        exchange(client, public, key, origin="http://127.0.0.1:5275/path").status_code
        == 422
    )
    assert exchange(client, public, key, visitor="email@example.com").status_code == 422
    assert exchange(client, public, key).status_code == 201
    assert (
        client.post(
            public + "/widget-tokens",
            headers={
                "Origin": "http://127.0.0.1:5275",
                "Authorization": f"Bearer {key['secret']}",
            },
            json={
                "visitor_session_id": "a" * 40,
                "site_origin": "http://127.0.0.1:5275",
            },
        ).status_code
        == 403
    )
    assert (
        client.get(
            public + "/status",
            headers={
                "Origin": "http://127.0.0.1:5274",
                "Authorization": f"Bearer {key['secret']}",
            },
        ).status_code
        == 403
    )
    assert (
        client.put(
            path + "/widget",
            headers={"If-Match": '"2"'},
            json={
                "enabled": False,
                "allowed_origins": [],
                "branding": {
                    "title": "Support",
                    "greeting": "Ask",
                    "color": "blue",
                    "position": "right",
                },
            },
        ).status_code
        == 412
    )


def test_visitor_scope_replay_revocation_and_pause(management_api, monkeypatch):
    client, connection, path, public, key = setup_widget(management_api, monkeypatch)
    first = exchange(client, public, key, "a" * 40).json()["token"]
    refreshed = exchange(client, public, key, "a" * 40).json()["token"]
    other = exchange(client, public, key, "b" * 40).json()["token"]

    def browser(token):
        return {
            "Origin": "http://127.0.0.1:5274",
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "same-request",
        }

    endpoint = public + "/widget/questions"
    made = client.post(
        endpoint, headers=browser(first), json={"question": "What is the answer?"}
    )
    assert made.status_code == 202, made.text
    run = made.json()
    assert "/widget/questions/" in run["status_url"]
    replay = client.post(
        endpoint, headers=browser(refreshed), json={"question": "What is the answer?"}
    )
    assert replay.status_code == 200 and replay.json()["id"] == run["id"]
    assert (
        client.post(
            endpoint, headers=browser(refreshed), json={"question": "Different"}
        ).status_code
        == 409
    )
    assert client.get(run["status_url"], headers=browser(other)).status_code == 404
    assert client.get(run["status_url"], headers=browser(refreshed)).status_code == 200
    assert client.get(run["result_url"], headers=browser(refreshed)).status_code == 202
    with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
        stored = session.scalar(
            select(DeployedAnswerRun).where(DeployedAnswerRun.id == run["id"])
        )
        assert (
            stored.caller_kind == "widget"
            and stored.widget_visitor_binding
            and stored.client_id != key["client_id"]
        )
        assert "a" * 40 not in stored.widget_visitor_binding
        token_row = session.scalar(
            select(WidgetToken).where(WidgetToken.client_id == stored.client_id)
        )
        assert (
            token_row.token_hash != first
            and token_row.site_origin == "http://127.0.0.1:5275"
        )
        token_row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    assert (
        client.get(public + "/widget/status", headers=browser(first)).status_code == 401
    )
    assert (
        client.post(public + "/widget/revoke", headers=browser(refreshed)).status_code
        == 204
    )
    assert client.get(run["status_url"], headers=browser(refreshed)).status_code == 401
    paused = client.post(path + "/pause", headers={"If-Match": '"3"'})
    assert paused.status_code == 200
    assert (
        client.post(
            endpoint, headers=browser(other), json={"question": "New question"}
        ).status_code
        == 409
    )
    assert client.get(run["status_url"], headers=browser(other)).status_code == 404
    # Customer logout revokes every token from that login session, including renewals.
    revoked = client.post(
        public + "/widget-tokens/revoke-session",
        headers={"Authorization": f"Bearer {key['secret']}"},
        json={"visitor_session_id": "b" * 40, "site_origin": "http://127.0.0.1:5275"},
    )
    assert revoked.status_code == 204
    assert (
        client.get(public + "/widget/status", headers=browser(other)).status_code == 401
    )
    assert client.post(path + f"/keys/{key['id']}/revoke").status_code == 200
    assert exchange(client, public, key).status_code == 401


def test_cors_and_settings_roles(management_api, monkeypatch):
    from app.core.auth import current_principal
    from app.main import app

    client, _, path, public, key = setup_widget(management_api, monkeypatch)
    token = exchange(client, public, key).json()["token"]
    endpoint = public + "/widget/status"
    assert (
        client.options(
            endpoint,
            headers={
                "Origin": "http://127.0.0.1:5274",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        ).status_code
        == 204
    )
    assert (
        client.options(
            endpoint,
            headers={
                "Origin": "http://127.0.0.1:5274.evil.test",
                "Access-Control-Request-Method": "GET",
            },
        ).status_code
        == 403
    )
    assert (
        client.get(endpoint, headers={"Authorization": f"Bearer {token}"}).status_code
        == 403
    )
    allowed = client.get(
        endpoint,
        headers={"Origin": "http://127.0.0.1:5274", "Authorization": f"Bearer {token}"},
    )
    assert (
        allowed.status_code == 200
        and allowed.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5274"
    )
    client0, _, _, _, _, _, _, identities, principal = management_api
    app.dependency_overrides[current_principal] = lambda: principal(
        identities[1], "editor"
    )
    assert client0.get(path + "/widget").status_code == 200
    assert (
        client0.put(
            path + "/widget",
            headers={"If-Match": '"3"'},
            json={
                "enabled": False,
                "allowed_origins": [],
                "branding": {
                    "title": "A",
                    "greeting": "",
                    "color": "blue",
                    "position": "right",
                },
            },
        ).status_code
        == 403
    )
    assert client0.post(path + "/widget/revoke-sessions").status_code == 403
    app.dependency_overrides[current_principal] = lambda: principal(
        identities[0], "owner", "org_b"
    )
    assert client0.get(path + "/widget").status_code == 404
    assert client0.post(path + "/widget/revoke-sessions").status_code == 404


def test_token_is_bound_to_deployment_and_survives_key_rotation_only_until_revoke(
    management_api, monkeypatch
):
    client, _, path, public, key = setup_widget(management_api, monkeypatch)
    original = exchange(client, public, key).json()["token"]
    browser = {
        "Origin": "http://127.0.0.1:5274",
        "Authorization": f"Bearer {original}",
    }
    assert client.get(public + "/widget/status", headers=browser).status_code == 200
    altered = original[:-1] + ("A" if original[-1] != "A" else "B")
    assert (
        client.get(
            public + "/widget/status",
            headers={**browser, "Authorization": f"Bearer {altered}"},
        ).status_code
        == 401
    )

    project, pipe, version, index = (
        management_api[2],
        management_api[4],
        management_api[5],
        management_api[6],
    )
    sibling = client.post(
        f"/api/projects/{project.id}/answer-deployments",
        json={
            "name": "Sibling",
            "pipeline_id": str(pipe.id),
            "pipeline_version_id": str(version.id),
            "index_id": str(index.id),
        },
    )
    assert sibling.status_code == 201, sibling.text
    sibling_public = f"/v1/answer-deployments/{sibling.json()['id']}"
    assert (
        client.get(sibling_public + "/widget/status", headers=browser).status_code
        == 401
    )
    assert exchange(client, sibling_public, key).status_code == 401

    rotated = client.post(path + f"/keys/{key['id']}/rotate")
    assert rotated.status_code == 201, rotated.text
    replacement = rotated.json()
    assert client.get(public + "/widget/status", headers=browser).status_code == 200
    next_token = exchange(client, public, replacement).json()["token"]
    assert client.post(path + f"/keys/{key['id']}/revoke").status_code == 200
    assert client.get(public + "/widget/status", headers=browser).status_code == 401
    assert (
        client.get(
            public + "/widget/status",
            headers={**browser, "Authorization": f"Bearer {next_token}"},
        ).status_code
        == 200
    )


def test_archive_denies_active_widget_token(management_api, monkeypatch):
    client, _, path, public, key = setup_widget(management_api, monkeypatch)
    token = exchange(client, public, key).json()["token"]
    archived = client.post(
        path + "/archive", headers={"If-Match": '"3"'}, json={"reason": "test"}
    )
    assert archived.status_code == 200, archived.text
    browser = {
        "Origin": "http://127.0.0.1:5274",
        "Authorization": f"Bearer {token}",
    }
    # Archive revokes deployment keys, which also invalidates issued widget tokens.
    assert client.get(public + "/widget/status", headers=browser).status_code == 401
    assert exchange(client, public, key).status_code in (409, 410)


def test_exchange_and_visitor_rates_are_independent(management_api, monkeypatch):
    client, _, _, public, key = setup_widget(management_api, monkeypatch)
    monkeypatch.setattr(settings, "widget_exchange_rpm", 1)
    first = exchange(client, public, key)
    assert first.status_code == 201
    assert exchange(client, public, key, visitor="b" * 40).status_code == 429

    monkeypatch.setattr(settings, "widget_exchange_rpm", 20)
    second = exchange(client, public, key, visitor="b" * 40)
    assert second.status_code == 201
    monkeypatch.setattr(settings, "widget_visitor_rpm", 1)
    route = public + "/widget/questions"

    def headers(token, key_value):
        return {
            "Origin": "http://127.0.0.1:5274",
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": key_value,
        }

    token_a = first.json()["token"]
    token_b = second.json()["token"]
    assert (
        client.post(
            route, headers=headers(token_a, "rate-a1"), json={"question": "One"}
        ).status_code
        == 202
    )
    assert (
        client.post(
            route, headers=headers(token_a, "rate-a2"), json={"question": "Two"}
        ).status_code
        == 429
    )
    assert (
        client.post(
            route,
            headers=headers(token_b, "rate-b1"),
            json={"question": "Another visitor"},
        ).status_code
        == 202
    )
