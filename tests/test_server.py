"""The webhook route is only reachable once mounted here: prove the mount works."""

from __future__ import annotations

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from cerebro.server import app


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_healthz():
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_webhook_route_is_mounted_and_rejects_bad_signature(monkeypatch):
    monkeypatch.setattr("cerebro.github.webhook.settings.github_webhook_secret", "s3cret")
    client = TestClient(app)
    body = json.dumps({"ok": True}).encode()
    response = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": "sha256=deadbeef", "X-GitHub-Event": "workflow_run"},
    )
    assert response.status_code == 401


def test_webhook_ignores_non_workflow_run_events(monkeypatch):
    monkeypatch.setattr("cerebro.github.webhook.settings.github_webhook_secret", "s3cret")
    client = TestClient(app)
    body = json.dumps({"ok": True}).encode()
    response = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body, "s3cret"), "X-GitHub-Event": "ping"},
    )
    assert response.status_code == 200
    assert response.json() == {"handled": False, "reason": "ignored_event", "event": "ping"}
