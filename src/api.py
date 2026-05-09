"""FastAPI inference service for the Heart Disease classifier.

Endpoints
---------
POST /predict    JSON body -> {prediction, probability, confidence, label, model_version}
GET  /health     liveness probe
GET  /ready      readiness probe (verifies the model has loaded)
GET  /metrics    Prometheus-format metrics (requests, latency, predictions counter)
GET  /           service banner with version
GET  /docs       Swagger UI (auto-generated)

Privacy / security notes
------------------------
* Input features are NOT logged in plaintext: only the request id, the
  prediction, and the probability are emitted. This matches the privacy
  guidance for handling PHI-adjacent data.
* All errors return a generic message; the full traceback stays in
  server logs.
* Pydantic enforces type + range validation at the boundary.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, ConfigDict, Field

from . import __version__

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
log = logging.getLogger("api")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_PATH = PROJECT_ROOT / "artifacts" / "models" / "model.pkl"
MODEL_PATH = Path(os.getenv("MODEL_PATH", DEFAULT_MODEL_PATH))


PREDICTION_COUNTER = Counter(
    "predictions_total",
    "Total predictions served, partitioned by predicted class.",
    labelnames=("predicted_class",),
)
PREDICTION_LATENCY = Histogram(
    "prediction_latency_seconds",
    "Latency of /predict in seconds.",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)


class HeartDiseaseFeatures(BaseModel):
    """Input schema mirroring the UCI Heart Disease feature set."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
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
        },
    )

    age: int = Field(..., ge=1, le=120, description="Age in years")
    sex: Literal[0, 1] = Field(..., description="0 = female, 1 = male")
    cp: Literal[0, 1, 2, 3, 4] = Field(..., description="Chest pain type (1-4)")
    trestbps: float = Field(..., ge=50, le=260, description="Resting blood pressure (mm Hg)")
    chol: float = Field(..., ge=80, le=700, description="Serum cholesterol (mg/dl)")
    fbs: Literal[0, 1] = Field(..., description="Fasting blood sugar > 120 mg/dl")
    restecg: Literal[0, 1, 2] = Field(..., description="Resting ECG results")
    thalach: float = Field(..., ge=50, le=250, description="Maximum heart rate achieved")
    exang: Literal[0, 1] = Field(..., description="Exercise-induced angina")
    oldpeak: float = Field(..., ge=0, le=10, description="ST depression induced by exercise")
    slope: Literal[1, 2, 3] = Field(..., description="Slope of the peak exercise ST segment")
    ca: Literal[0, 1, 2, 3] = Field(..., description="Number of major vessels (0-3)")
    thal: Literal[3, 6, 7] = Field(
        ..., description="Thalassemia type: 3=normal, 6=fixed defect, 7=reversible"
    )


class PredictionResponse(BaseModel):
    request_id: str
    prediction: int = Field(..., description="0 = no disease, 1 = disease")
    probability: float = Field(..., ge=0, le=1, description="Probability of class 1")
    confidence: float = Field(..., ge=0, le=1, description="Confidence of predicted class")
    label: str
    model_version: str


def _load_model():
    """Load the persisted scikit-learn pipeline.

    Raised errors propagate so the readiness probe can surface them.
    """
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model artifact not found at {MODEL_PATH}. "
            "Run `python -m src.train` first or set MODEL_PATH to a valid file."
        )
    log.info("Loading model from %s", MODEL_PATH)
    return joblib.load(MODEL_PATH)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Eagerly load the model at startup so failures appear in liveness logs."""
    try:
        app.state.model = _load_model()
        app.state.model_loaded = True
        log.info("Model loaded successfully.")
    except Exception as exc:  # noqa: BLE001
        # We do NOT crash the process — readiness will return 503 instead,
        # which is the correct Kubernetes pattern: pod stays alive while
        # the deployment surfaces a clear failure mode.
        app.state.model = None
        app.state.model_loaded = False
        app.state.model_error = str(exc)
        log.error("Failed to load model at startup: %s", exc)
    yield


app = FastAPI(
    title="Heart Disease Prediction API",
    version=__version__,
    description=(
        "Production-ready ML service that classifies heart disease risk from "
        "patient features. Built for the BITS Pilani MLOps assignment."
    ),
    lifespan=lifespan,
)

# Prometheus instrumentation auto-exposes /metrics with HTTP latency, status
# code, and request count series.
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.headers["x-request-id"] = request_id
    log.info(
        'request_id=%s method=%s path=%s status=%s duration_ms=%.2f',
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log full error details server-side, return generic message to client."""
    request_id = getattr(request.state, "request_id", "unknown")
    log.exception("Unhandled error request_id=%s", request_id)
    return JSONResponse(
        status_code=500,
        content={
            "request_id": request_id,
            "detail": "Internal server error.",
        },
    )


@app.get("/", tags=["meta"])
def root() -> dict[str, Any]:
    return {
        "service": "Heart Disease Prediction API",
        "version": __version__,
        "endpoints": ["/predict", "/health", "/ready", "/metrics", "/docs"],
    }


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe — always returns OK if the process is up."""
    return {"status": "ok"}


@app.get("/ready", tags=["meta"])
def ready() -> dict[str, Any]:
    """Readiness probe — only returns 200 once the model artifact is loaded."""
    if not getattr(app.state, "model_loaded", False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "reason": getattr(app.state, "model_error", "model not loaded"),
            },
        )
    return {"status": "ready", "model_path": str(MODEL_PATH)}


@app.post("/predict", response_model=PredictionResponse, tags=["inference"])
def predict(features: HeartDiseaseFeatures, request: Request) -> PredictionResponse:
    """Score a single patient record."""
    if not getattr(app.state, "model_loaded", False):
        raise HTTPException(
            status_code=503,
            detail="Model not loaded. Train the model and ensure MODEL_PATH is correct.",
        )

    request_id: str = getattr(request.state, "request_id", uuid.uuid4().hex[:12])

    payload = pd.DataFrame([features.model_dump()])

    with PREDICTION_LATENCY.time():
        try:
            proba = float(app.state.model.predict_proba(payload)[0, 1])
        except Exception as exc:  # noqa: BLE001
            log.error("Inference failed request_id=%s err=%s", request_id, exc)
            raise HTTPException(status_code=500, detail="Inference failed.") from exc
    prediction = int(np.round(proba))
    confidence = proba if prediction == 1 else 1.0 - proba

    PREDICTION_COUNTER.labels(predicted_class=str(prediction)).inc()
    log.info(
        'request_id=%s prediction=%d probability=%.4f',
        request_id,
        prediction,
        proba,
    )
    return PredictionResponse(
        request_id=request_id,
        prediction=prediction,
        probability=round(proba, 4),
        confidence=round(confidence, 4),
        label="Heart disease" if prediction == 1 else "No heart disease",
        model_version=__version__,
    )
