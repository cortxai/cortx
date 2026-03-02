"""Smoke tests for the Ingress API (Phase 0).

Tests run against the FastAPI TestClient — no Docker, no Ollama required.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_ingest_returns_stub():
    response = client.post("/ingest", json={"input": "hello"})
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "stub"
    assert body["response"] == "Phase 0 OK"


def test_ingest_rejects_missing_input():
    response = client.post("/ingest", json={})
    assert response.status_code == 422


def test_chat_completions_returns_200():
    payload = {
        "model": "agentic",
        "messages": [{"role": "user", "content": "hello"}],
    }
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    assert len(body["choices"]) == 1
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["choices"][0]["message"]["content"] == "Phase 0 OK"


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
