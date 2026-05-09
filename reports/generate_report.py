"""Generate the 10-page final assignment report as a Word document.

Usage:
    python reports/generate_report.py

Outputs:
    reports/Final_Report.docx

The report intentionally references plots that exist in:
    artifacts/plots/eda/   (created by notebooks/01_eda.ipynb)
    artifacts/plots/       (created by src/train.py)
    reports/architecture.png  (created by reports/architecture_diagram.py)

If a plot is missing the section is still emitted with a placeholder note,
so the script never fails the build.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "artifacts"
PLOTS = ARTIFACTS / "plots"
EDA_PLOTS = PLOTS / "eda"
METRICS_JSON = ARTIFACTS / "models" / "metrics.json"
ARCH = ROOT / "reports" / "architecture.png"
OUT_PATH = ROOT / "reports" / "Final_Report.docx"


def _heading(doc: Document, text: str, level: int = 1):
    h = doc.add_heading(text, level=level)
    for run in h.runs:
        run.font.color.rgb = RGBColor(0x1F, 0x3B, 0x73)
    return h


def _para(doc: Document, text: str, *, bold: bool = False, italic: bool = False, size: int = 11):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    return p


def _bullet(doc: Document, text: str):
    p = doc.add_paragraph(text, style="List Bullet")
    for r in p.runs:
        r.font.size = Pt(11)
    return p


def _image(doc: Document, path: Path, caption: str, width_cm: float = 15.0):
    if not path.exists():
        _para(doc, f"[ Plot pending: run the notebook / training pipeline to generate {path.name} ]", italic=True)
        return
    doc.add_picture(str(path), width=Cm(width_cm))
    last = doc.paragraphs[-1]
    last.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = cap.add_run(caption)
    r.italic = True
    r.font.size = Pt(9)


def _metrics_table(doc: Document, summary: dict):
    leaderboard = summary.get("leaderboard", [])
    if not leaderboard:
        _para(doc, "[ Train the models with `python -m src.train` to populate metrics. ]", italic=True)
        return

    table = doc.add_table(rows=1, cols=6)
    table.style = "Light Grid Accent 1"
    hdr = table.rows[0].cells
    headers = ["Model", "Accuracy", "Precision", "Recall", "F1", "ROC-AUC"]
    for cell, label in zip(hdr, headers):
        cell.text = label
        for run in cell.paragraphs[0].runs:
            run.bold = True
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    for row in leaderboard:
        m = row.get("metrics", {})
        cells = table.add_row().cells
        cells[0].text = row["model"]
        cells[1].text = f"{m.get('accuracy', 0):.3f}"
        cells[2].text = f"{m.get('precision', 0):.3f}"
        cells[3].text = f"{m.get('recall', 0):.3f}"
        cells[4].text = f"{m.get('f1', 0):.3f}"
        cells[5].text = f"{m.get('roc_auc', 0):.3f}"


def _load_metrics() -> dict:
    if not METRICS_JSON.exists():
        return {}
    return json.loads(METRICS_JSON.read_text())


def build_report() -> Path:
    doc = Document()

    # Default styles
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    # ---------------- Cover page ----------------
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = title.add_run("MLOps Experiential Learning Assignment")
    r.bold = True
    r.font.size = Pt(24)
    r.font.color.rgb = RGBColor(0x1F, 0x3B, 0x73)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = sub.add_run("End-to-End ML Model Development, CI/CD, and Production Deployment")
    r.font.size = Pt(14)
    r.italic = True

    for _ in range(2):
        doc.add_paragraph()

    if ARCH.exists():
        doc.add_picture(str(ARCH), width=Cm(15))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER

    for _ in range(2):
        doc.add_paragraph()

    info_lines = [
        "Course: MLOps (S2-25_AMLCSZG523)",
        "Programme: M.Tech, BITS Pilani (Work Integrated Learning)",
        "Student Name: Kavya Damera",
        "BITS ID: 2025cs05037",
        f"Date of submission: {datetime.now().strftime('%d %B %Y')}",
        "Dataset: UCI Heart Disease (Cleveland)",
        "Repository: https://github.com/BITS-2025cs05037/heart-disease-mlops",
    ]
    for line in info_lines:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(line)
        run.font.size = Pt(12)

    doc.add_page_break()

    # ---------------- Section 1: Executive Summary ----------------
    _heading(doc, "1. Executive Summary", level=1)
    _para(
        doc,
        "This report documents the end-to-end MLOps solution built around the UCI Heart "
        "Disease dataset. The deliverable is a production-ready service that predicts the "
        "presence of heart disease from 13 patient features. Every stage of the workflow — "
        "data acquisition, model development, experiment tracking, packaging, automated "
        "testing, containerisation, Kubernetes deployment, and monitoring — has been "
        "automated and is reproducible from a clean checkout via a single GitHub Actions "
        "pipeline.",
    )
    _para(doc, "Key engineering decisions:", bold=True)
    _bullet(doc, "Single sklearn Pipeline encapsulates preprocessing AND the classifier so the API never desynchronises from training.")
    _bullet(doc, "MLflow tracks every grid-search candidate; the best model is registered under a stable name to decouple training from deployment.")
    _bullet(doc, "FastAPI exposes /predict, /health, /ready and Prometheus /metrics; Pydantic validates every field at the trust boundary.")
    _bullet(doc, "Multi-stage hardened Docker image runs as a non-root user with a read-only root filesystem.")
    _bullet(doc, "Helm chart + plain manifests cover both Minikube (local) and managed Kubernetes deployments.")
    _bullet(doc, "GitHub Actions runs lint, tests, a sanity training run, and a Docker smoke test on every push.")

    doc.add_page_break()

    # ---------------- Section 2: Problem Statement & Dataset ----------------
    _heading(doc, "2. Problem Statement & Dataset", level=1)
    _para(
        doc,
        "Cardio-vascular disease is the leading cause of mortality globally. The objective "
        "of this assignment is to build a binary classifier that estimates the probability "
        "of heart disease for a patient described by 13 routinely collected clinical "
        "features (age, sex, chest-pain type, resting BP, cholesterol, fasting blood sugar, "
        "resting ECG, max heart rate, exercise-induced angina, oldpeak, ST slope, number of "
        "major vessels, thalassemia type) and to expose this model as a cloud-ready API.",
    )
    _heading(doc, "2.1 Dataset description", level=2)
    _bullet(doc, "Source: UCI Machine Learning Repository — Heart Disease (Cleveland) dataset.")
    _bullet(doc, "Rows: ~303 patient records.")
    _bullet(doc, "Features: 13 numeric/categorical predictors.")
    _bullet(doc, "Target: original `num` (0–4) is binarised to 0 (no disease) vs 1 (disease).")
    _bullet(doc, "License: public (UCI).")
    _para(
        doc,
        "Acquisition is automated by `scripts/download_data.py`, which downloads from the "
        "UCI mirror, falls back to a GitHub mirror, prepends headers, replaces ‘?’ with NaN, "
        "casts numerics, drops rows with missing target, binarises the label and writes "
        "`data/processed/heart_disease.csv`.",
    )

    doc.add_page_break()

    # ---------------- Section 3: EDA ----------------
    _heading(doc, "3. Exploratory Data Analysis (Task 1 — 5 marks)", level=1)
    _para(
        doc,
        "EDA was performed in `notebooks/01_eda.ipynb`. The plots below were saved to "
        "`artifacts/plots/eda/` and are reproduced here.",
    )
    _image(doc, EDA_PLOTS / "class_balance.png", "Figure 1 — Target class balance.")
    _image(doc, EDA_PLOTS / "missing_values.png", "Figure 2 — Missingness audit.")
    _image(doc, EDA_PLOTS / "numeric_distributions.png", "Figure 3 — Numeric feature distributions split by class.")
    _image(doc, EDA_PLOTS / "correlation_heatmap.png", "Figure 4 — Correlation heatmap.")
    _image(doc, EDA_PLOTS / "categorical_distributions.png", "Figure 5 — Disease prevalence by categorical feature.")

    _heading(doc, "3.1 Findings", level=2)
    _bullet(doc, "Class balance is mild (~54% positive) — stratified splits used everywhere.")
    _bullet(doc, "Only `ca` and `thal` exhibit missingness; median / most-frequent imputation handles both.")
    _bullet(doc, "`oldpeak`, `thalach`, and `cp` are the strongest individual predictors and align with clinical literature.")
    _bullet(doc, "`chol` exhibits long-tail outliers, motivating evaluation of tree-based models alongside Logistic Regression.")

    doc.add_page_break()

    # ---------------- Section 4: Feature engineering & modelling ----------------
    _heading(doc, "4. Feature Engineering & Model Development (Task 2 — 8 marks)", level=1)
    _para(
        doc,
        "All preprocessing logic is encapsulated in `src/preprocessing.py` as a "
        "scikit-learn `ColumnTransformer`:",
    )
    _bullet(doc, "Numeric columns (age, trestbps, chol, thalach, oldpeak, ca) — median imputation + StandardScaler.")
    _bullet(doc, "Categorical columns (sex, cp, fbs, restecg, exang, slope, thal) — most-frequent imputation + OneHotEncoder(handle_unknown='ignore').")
    _bullet(doc, "Preprocessor + classifier are wrapped in a single sklearn Pipeline so deployment can never receive a mismatched feature schema.")

    _heading(doc, "4.1 Model catalogue and selection", level=2)
    _para(
        doc,
        "Three classifiers are compared with 5-fold StratifiedKFold cross-validation and "
        "GridSearchCV on ROC-AUC:",
    )
    _bullet(doc, "Logistic Regression — interpretable linear baseline (C and penalty tuned).")
    _bullet(doc, "Random Forest — non-linear, robust to outliers (n_estimators, max_depth, min_samples_split tuned).")
    _bullet(doc, "Gradient Boosting — strong tabular performer (n_estimators, learning_rate, max_depth tuned).")
    _para(
        doc,
        "The best model is selected by held-out test ROC-AUC and persisted to "
        "`artifacts/models/model.pkl`. The full leaderboard is recorded in "
        "`artifacts/models/metrics.json` and on the MLflow tracking server.",
    )

    summary = _load_metrics()
    if summary:
        _para(doc, f"Winning model: {summary.get('winner', 'TBD')}", bold=True)
    _metrics_table(doc, summary)

    _image(doc, PLOTS / "random_forest_confusion_matrix.png", "Figure 6 — Random Forest confusion matrix.", width_cm=10)
    _image(doc, PLOTS / "random_forest_roc.png", "Figure 7 — Random Forest ROC curve.", width_cm=10)

    doc.add_page_break()

    # ---------------- Section 5: MLflow ----------------
    _heading(doc, "5. Experiment Tracking with MLflow (Task 3 — 5 marks)", level=1)
    _para(
        doc,
        "Every grid-search candidate is logged to MLflow as an individual run with: "
        "model family, all hyper-parameters, mean CV ROC-AUC, all held-out metrics, "
        "confusion matrix PNG, ROC curve PNG, and feature importance PNG. The full "
        "Pipeline (preprocessor + classifier) is logged as an MLflow model artifact, "
        "guaranteeing the served model uses identical preprocessing.",
    )
    _bullet(doc, "Tracking URI: file:./mlruns (local) or any remote URI passed via --tracking-uri.")
    _bullet(doc, "Experiment name: heart-disease.")
    _bullet(doc, "After grid search the winner is registered under the stable name 'heart-disease-classifier' so deployment can fetch it without hard-coding a run id.")
    _para(doc, "Launch the MLflow UI locally with `make mlflow-ui` (port 5000).")
    _para(doc, "Required screenshot: ML flow UI showing the experiment, runs, registered model. (Place under `screenshots/mlflow-ui.png`.)", italic=True)

    doc.add_page_break()

    # ---------------- Section 6: Packaging ----------------
    _heading(doc, "6. Packaging & Reproducibility (Task 4 — 7 marks)", level=1)
    _bullet(doc, "Versions of every runtime dependency are pinned in `requirements.txt`; dev / test / lint dependencies live in `requirements-dev.txt`.")
    _bullet(doc, "The trained Pipeline is persisted with joblib at `artifacts/models/model.pkl` and additionally tracked as an MLflow model artifact.")
    _bullet(doc, "All preprocessing steps are part of the saved Pipeline, so inference clients only need to pass raw JSON — no manual feature engineering.")
    _bullet(doc, "Reproducible random_state defaults are exposed as constants in `src/data_loader.py` and surfaced via CLI flags on `src/train.py`.")
    _bullet(doc, "`Makefile` provides a single source of truth for setup, training, testing, and the report.")

    doc.add_page_break()

    # ---------------- Section 7: CI/CD ----------------
    _heading(doc, "7. CI/CD Pipeline & Automated Testing (Task 5 — 8 marks)", level=1)
    _para(doc, "Pytest suite covers four layers:", bold=True)
    _bullet(doc, "tests/test_data_loader.py — schema, stratified splits, reproducibility.")
    _bullet(doc, "tests/test_preprocessing.py — imputation, scaling, one-hot encoding, unknown-category handling.")
    _bullet(doc, "tests/test_model_io.py — joblib round-trip equivalence, dictionary-style inference.")
    _bullet(doc, "tests/test_api.py — /health, /ready, /metrics, /predict happy-path, request-id propagation, validation errors.")
    _para(doc, "GitHub Actions workflow (`.github/workflows/ci-cd.yml`) executes four sequential jobs on every push:", bold=True)
    _bullet(doc, "lint — ruff + black --check on src, tests, scripts.")
    _bullet(doc, "test — pytest with coverage; results uploaded as artifacts.")
    _bullet(doc, "train — downloads dataset, runs `python -m src.train --cv-splits 3`, uploads model.pkl, metrics.json and the MLflow run as build artifacts.")
    _bullet(doc, "docker — builds the production image with BuildKit cache, runs the container, smoke-tests /health, /ready, /predict.")
    _para(doc, "Required screenshot: green Actions run with all four jobs visible.", italic=True)

    doc.add_page_break()

    # ---------------- Section 8: Containerisation ----------------
    _heading(doc, "8. Containerisation (Task 6 — 5 marks)", level=1)
    _para(
        doc,
        "`docker/Dockerfile` is a multi-stage build that produces a minimal runtime image "
        "based on `python:3.11.10-slim-bookworm`. Hardening features:",
    )
    _bullet(doc, "Builder stage installs into a pre-built virtualenv copied into the runtime stage.")
    _bullet(doc, "Runtime stage runs as a non-root user (UID/GID 10001) with a writable /tmp tmpfs only.")
    _bullet(doc, "tini is used as PID 1 for correct signal handling.")
    _bullet(doc, "HEALTHCHECK invokes /health every 30s.")
    _bullet(doc, "All capabilities dropped, no-new-privileges enforced, read-only rootfs in compose & K8s.")
    _para(doc, "Build & run:", bold=True)
    p = doc.add_paragraph()
    p.add_run("docker build -f docker/Dockerfile -t heart-disease-api:latest .\n").font.name = "Consolas"
    p.add_run("docker run --rm -p 8000:8000 heart-disease-api:latest").font.name = "Consolas"

    _para(doc, "Required screenshot: terminal showing successful image build and a /predict response.", italic=True)

    doc.add_page_break()

    # ---------------- Section 9: K8s deployment ----------------
    _heading(doc, "9. Production Deployment (Task 7 — 7 marks)", level=1)
    _para(
        doc,
        "The service is deployed on Kubernetes via two interchangeable mechanisms: raw "
        "manifests in `k8s/` and a Helm chart in `helm/heart-disease/`. Both produce: "
        "Deployment (2 replicas, rolling update, liveness/readiness/startup probes, non-"
        "root pod security context, read-only root FS, resource requests/limits), Service "
        "(type LoadBalancer), Ingress (nginx, host `heart.local`), HPA (CPU 70%, memory "
        "80%, 2-6 replicas), and a default-deny NetworkPolicy with explicit allow rules.",
    )
    _para(doc, "Deploy on Minikube:", bold=True)
    p = doc.add_paragraph()
    for line in [
        "minikube start --cpus=4 --memory=4096",
        "minikube addons enable ingress metrics-server",
        "eval $(minikube docker-env)",
        "docker build -f docker/Dockerfile -t heart-disease-api:latest .",
        "kubectl apply -f k8s/",
        "kubectl get pods -n heart-disease -w",
        "minikube tunnel  # in another terminal",
    ]:
        run = p.add_run(line + "\n")
        run.font.name = "Consolas"
        run.font.size = Pt(10)

    _para(doc, "Or via Helm:", bold=True)
    p = doc.add_paragraph()
    p.add_run(
        "helm install heart-disease helm/heart-disease "
        "--namespace heart-disease --create-namespace"
    ).font.name = "Consolas"

    _para(doc, "Required screenshot set:", italic=True)
    _bullet(doc, "kubectl get pods,svc,ingress,hpa -n heart-disease")
    _bullet(doc, "Browser hitting http://heart.local/docs (Swagger UI)")
    _bullet(doc, "curl /predict response with prediction + probability")

    doc.add_page_break()

    # ---------------- Section 10: Monitoring ----------------
    _heading(doc, "10. Monitoring & Logging (Task 8 — 3 marks)", level=1)
    _para(doc, "API observability:", bold=True)
    _bullet(doc, "Structured one-line JSON logs on stdout (ts, level, request_id, method, path, status, duration_ms).")
    _bullet(doc, "Every response carries an `x-request-id` header (generated if missing) so logs can be correlated end-to-end.")
    _bullet(doc, "Custom Prometheus counters: `predictions_total{predicted_class}` and `prediction_latency_seconds`.")
    _bullet(doc, "Auto-instrumented HTTP metrics via `prometheus-fastapi-instrumentator`.")
    _para(doc, "Local dashboard stack:", bold=True)
    p = doc.add_paragraph()
    p.add_run("docker compose up --build").font.name = "Consolas"
    _para(doc, "→ Prometheus on :9090, Grafana on :3000 (admin/admin), pre-provisioned dashboard `Heart Disease API — MLOps Monitoring`.")
    _para(doc, "Required screenshot: Grafana dashboard with traffic on it.", italic=True)

    doc.add_page_break()

    # ---------------- Section 11: Architecture ----------------
    _heading(doc, "11. Architecture Diagram (Task 9 — 2 marks)", level=1)
    _image(doc, ARCH, "Figure 8 — End-to-end architecture (developer → CI/CD → K8s → observability).")

    # ---------------- Section 12: Setup / Run instructions ----------------
    _heading(doc, "12. Setup & Run Instructions", level=1)
    _para(doc, "Clone, install, train, test, run:", bold=True)
    p = doc.add_paragraph()
    for line in [
        "git clone https://github.com/BITS-2025cs05037/heart-disease-mlops.git",
        "cd heart-disease-mlops",
        "make install-dev",
        "make download-data",
        "make train",
        "make test",
        "make api          # http://localhost:8000/docs",
        "make mlflow-ui    # http://localhost:5000",
        "make docker-build && make docker-run",
        "kubectl apply -f k8s/",
    ]:
        r = p.add_run(line + "\n")
        r.font.name = "Consolas"
        r.font.size = Pt(10)

    _heading(doc, "12.1 Repository structure", level=2)
    structure = (
        "heart-disease-mlops/\n"
        "├── .github/workflows/ci-cd.yml      CI/CD pipeline\n"
        "├── data/{raw,processed}             dataset (download script)\n"
        "├── notebooks/01_eda.ipynb           EDA notebook\n"
        "├── src/                             data_loader, preprocessing, train, evaluate, api\n"
        "├── tests/                           pytest suite\n"
        "├── docker/Dockerfile                multi-stage hardened image\n"
        "├── k8s/                             Deployment + Service + Ingress + HPA + NetworkPolicy\n"
        "├── helm/heart-disease/              Helm chart\n"
        "├── monitoring/                      Prometheus + Grafana stack\n"
        "├── reports/                         this report + architecture diagram\n"
        "├── screenshots/                     UI evidence\n"
        "├── scripts/download_data.py         dataset downloader\n"
        "├── docker-compose.yml               local API + Prometheus + Grafana\n"
        "├── Makefile                         single source of truth\n"
        "└── requirements*.txt                pinned deps\n"
    )
    p = doc.add_paragraph(structure)
    for run in p.runs:
        run.font.name = "Consolas"
        run.font.size = Pt(9)

    # ---------------- Section 13: Conclusion ----------------
    _heading(doc, "13. Conclusion", level=1)
    _para(
        doc,
        "The deliverable demonstrates every stage of a production MLOps lifecycle on a "
        "real-world clinical dataset. The combination of pinned dependencies, a single "
        "sklearn Pipeline, MLflow tracking & registry, hardened Docker image, declarative "
        "Kubernetes manifests / Helm chart, and a Prometheus/Grafana observability stack "
        "satisfies the assignment's production-readiness requirements: every script runs "
        "from a clean checkout, the pipeline fails on lint or test errors, and the served "
        "model is byte-identical to the one logged during training.",
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT_PATH)
    return OUT_PATH


if __name__ == "__main__":
    out = build_report()
    print(f"Wrote {out}")
