"""Tests for the FastAPI service.

We override the model loader at startup so the tests do not depend on a
trained pickle file — the lifespan hook will install a session-scoped
trained pipeline produced from synthetic data instead.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

from src import api as api_module


@pytest.fixture
def client(trained_pipeline) -> TestClient:
    """Build a TestClient whose lifespan installs the synthetic pipeline."""

    @asynccontextmanager
    async def _lifespan(app):
        app.state.model = trained_pipeline
        app.state.model_loaded = True
        yield

    api_module.app.router.lifespan_context = _lifespan
    with TestClient(api_module.app) as c:
        yield c


def _example_payload() -> dict:
    return {
        "age": 63,
        "sex": 1,
        "cp": 3,
        "trestbps": 145,
        "chol": 233,
        "fbs": 1,
        "restecg": 0,
        "thalach": 150,
        "exang": 0,
        "oldpeak": 2.3,
        "slope": 1,
        "ca": 0,
        "thal": 6,
    }


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_root_lists_endpoints(client):
    r = client.get("/")
    assert r.status_code == 200
    payload = r.json()
    assert "endpoints" in payload
    assert "/predict" in payload["endpoints"]


def test_metrics_endpoint_returns_prometheus_format(client):
    # Hit /predict once to ensure custom metrics have data
    client.post("/predict", json=_example_payload())
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "predictions_total" in r.text
    assert "prediction_latency_seconds" in r.text


def test_predict_happy_path(client):
    r = client.post("/predict", json=_example_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["prediction"] in (0, 1)
    assert 0.0 <= body["probability"] <= 1.0
    assert 0.0 <= body["confidence"] <= 1.0
    assert body["label"] in ("Heart disease", "No heart disease")
    assert "request_id" in body
    assert body["model_version"]


def test_predict_request_id_round_trips(client):
    r = client.post(
        "/predict",
        json=_example_payload(),
        headers={"x-request-id": "abc-123"},
    )
    assert r.status_code == 200
    assert r.headers.get("x-request-id") == "abc-123"
    assert r.json()["request_id"] == "abc-123"


def test_predict_rejects_unknown_field(client):
    payload = _example_payload()
    payload["unknown_field"] = "boom"
    r = client.post("/predict", json=payload)
    assert r.status_code == 422


def test_predict_rejects_out_of_range(client):
    payload = _example_payload()
    payload["age"] = -5
    r = client.post("/predict", json=payload)
    assert r.status_code == 422


def test_predict_rejects_invalid_categorical_level(client):
    payload = _example_payload()
    payload["thal"] = 99  # not in {3, 6, 7}
    r = client.post("/predict", json=payload)
    assert r.status_code == 422
