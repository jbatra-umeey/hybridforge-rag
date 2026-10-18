from fastapi.testclient import TestClient

from hybridforge.api import create_app
from hybridforge.models import Principal


def headers(settings):
    return {"Authorization": "Bearer " + settings.demo_token}


def test_api_full_lifecycle(settings, document):
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/ready").status_code == 200
        assert client.get("/").status_code == 200
        assert client.get("/v1/documents").status_code == 401
        assert (
            client.put(
                "/v1/documents", json=document.model_dump(), headers=headers(settings)
            ).status_code
            == 200
        )
        answer = client.post(
            "/v1/query", json={"question": "ERR_BRIDGE_042"}, headers=headers(settings)
        )
        assert answer.status_code == 200
        assert answer.json()["status"] == "answered"
        assert answer.headers["cache-control"] == "no-store"
        assert client.get("/metrics", headers=headers(settings)).status_code == 200
        assert (
            client.delete(
                "/v1/documents/runbook?expected_version=1", headers=headers(settings)
            ).status_code
            == 204
        )


def test_bad_token_and_untrusted_tenant(settings):
    with TestClient(create_app(settings)) as client:
        assert (
            client.get("/v1/documents", headers={"Authorization": "Bearer wrong"}).status_code
            == 401
        )
        result = client.post(
            "/v1/query", json={"question": "bridge", "tenant": "other"}, headers=headers(settings)
        )
        assert result.status_code == 422
        assert (
            client.put(
                "/v1/documents", json={"document_id": "../secret"}, headers=headers(settings)
            ).status_code
            == 422
        )


def test_large_body_rejected(settings):
    with TestClient(create_app(settings)) as client:
        assert (
            client.put(
                "/v1/documents", content=b"x" * 700001, headers=headers(settings)
            ).status_code
            == 413
        )


def test_reader_cannot_write(settings, document, monkeypatch):
    app = create_app(settings)
    monkeypatch.setattr(app.state.auth, "authenticate", lambda _: Principal("demo", "reader"))
    with TestClient(app) as client:
        assert (
            client.put(
                "/v1/documents", json=document.model_dump(), headers=headers(settings)
            ).status_code
            == 403
        )
        assert client.get("/metrics", headers=headers(settings)).status_code == 403


def test_version_conflict_is_409(settings, document):
    with TestClient(create_app(settings)) as client:
        client.put("/v1/documents", json=document.model_dump(), headers=headers(settings))
        body = document.model_dump()
        body["text"] = "New document body."
        assert client.put("/v1/documents", json=body, headers=headers(settings)).status_code == 409
