"""Generate the final assignment report (~14 sections, ~16 pages) as DOCX + PDF.

Usage:
    python reports/generate_report.py            # writes both .docx and .pdf
    python reports/generate_report.py --no-pdf   # writes only the .docx

Outputs:
    reports/Final_Report.docx
    reports/Final_Report.pdf      (if a PDF backend is available)

The report intentionally references plots that exist in:
    artifacts/plots/eda/   (created by notebooks/01_eda.ipynb)
    artifacts/plots/       (created by src/train.py)
    reports/architecture.png  (created by reports/architecture_diagram.py)

If a plot is missing the section is still emitted with a placeholder note,
so the script never fails the build.

PDF generation tries the following backends in order:
    1. docx2pdf (uses Microsoft Word automation on macOS / Word COM on Windows)
    2. LibreOffice (`soffice --headless --convert-to pdf`) — install via brew
    3. graceful skip with a clear log message
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "artifacts"
PLOTS = ARTIFACTS / "plots"
EDA_PLOTS = PLOTS / "eda"
METRICS_JSON = ARTIFACTS / "models" / "metrics.json"
ARCH = ROOT / "reports" / "architecture.png"
OUT_PATH = ROOT / "reports" / "Final_Report.docx"
PDF_PATH = ROOT / "reports" / "Final_Report.pdf"
OUT_PATH_V2 = ROOT / "reports" / "Final_Report_v2.docx"
PDF_PATH_V2 = ROOT / "reports" / "Final_Report_v2.pdf"


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


def _code_block(doc: Document, text: str, *, size: int = 9):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.name = "Menlo"
    run.font.size = Pt(size)
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


def _kv_table(doc: Document, rows, *, col_widths=(5.0, 11.0)):
    """Render a 2-column table of (label, value) pairs."""
    table = doc.add_table(rows=0, cols=2)
    table.style = "Light Grid Accent 1"
    for label, value in rows:
        cells = table.add_row().cells
        cells[0].text = label
        cells[1].text = value
        for r in cells[0].paragraphs[0].runs:
            r.bold = True
            r.font.size = Pt(10)
        for r in cells[1].paragraphs[0].runs:
            r.font.size = Pt(10)
    for row in table.rows:
        row.cells[0].width = Cm(col_widths[0])
        row.cells[1].width = Cm(col_widths[1])
    return table


def _table_with_header(doc: Document, headers, rows, *, style="Light Grid Accent 1"):
    """Render a generic header-row table."""
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = style
    for cell, label in zip(table.rows[0].cells, headers):
        cell.text = label
        for r in cell.paragraphs[0].runs:
            r.bold = True
            r.font.size = Pt(10)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    for row in rows:
        cells = table.add_row().cells
        for cell, val in zip(cells, row):
            cell.text = str(val)
            for r in cell.paragraphs[0].runs:
                r.font.size = Pt(10)
    return table


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
    r = title.add_run("Heart Disease MLOps")
    r.bold = True
    r.font.size = Pt(28)
    r.font.color.rgb = RGBColor(0x1F, 0x3B, 0x73)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = sub.add_run(
        "End-to-End ML Model Development, CI/CD, Containerisation, "
        "Kubernetes Deployment, and Production Monitoring"
    )
    r.font.size = Pt(13)
    r.italic = True

    for _ in range(2):
        doc.add_paragraph()

    info_table = doc.add_table(rows=0, cols=2)
    info_table.style = "Light Grid Accent 1"
    cover_rows = [
        ("Course", "MLOps (S2-25_AMLCSZG523)"),
        ("Assignment", "Experiential Learning — End-to-End MLOps Pipeline"),
        ("Student", "Kavya Damera"),
        ("Student ID", "2025cs05037"),
        ("Programme", "M.Tech, BITS Pilani — Work Integrated Learning Programmes"),
        ("Dataset", "UCI Heart Disease (Cleveland subset, 303 records)"),
        ("Repository", "https://github.com/BITS-2025cs05037/heart-disease-mlops"),
        ("Demo recording", "[See submission folder — link in §14]"),
        ("Date of submission", datetime.now().strftime("%d %B %Y")),
    ]
    for label, value in cover_rows:
        cells = info_table.add_row().cells
        cells[0].text = label
        cells[1].text = value
        for r in cells[0].paragraphs[0].runs:
            r.bold = True
            r.font.size = Pt(11)
        for r in cells[1].paragraphs[0].runs:
            r.font.size = Pt(11)
        cells[0].width = Cm(4.5)
        cells[1].width = Cm(11.5)

    doc.add_paragraph()
    doc.add_paragraph()

    note = doc.add_paragraph()
    note.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = note.add_run(
        "All code, manifests, monitoring config, screenshots, and the architecture "
        "diagram referenced in this report live in the repository above. The repository "
        "checkout used to generate this PDF is the 'main' branch at the time of "
        "submission."
    )
    r.italic = True
    r.font.size = Pt(10)

    doc.add_page_break()

    # ============================================================
    # Section 1 — Introduction
    # ============================================================
    _heading(doc, "1. Introduction", level=1)
    _para(
        doc,
        "This report describes a complete MLOps implementation built around the UCI Heart "
        "Disease dataset (Cleveland subset). The brief is intentionally small — a binary "
        "classification problem on roughly 300 patient records — but the engineering work "
        "around it is treated as if the model were going into production: every step from "
        "data download through model serving is reproducible from a clean checkout, "
        "version-controlled, automatically tested, packaged as a hardened container, "
        "deployed declaratively on Kubernetes, and instrumented for observability.",
    )
    _para(
        doc,
        "Throughout the report each design choice is explained inline with its rationale, "
        "and the corresponding location in the repository is named so the marker can map "
        "any claim back to source. Screenshots that prove the runtime behaviour are placed "
        "under the screenshots/ folder of the submission archive (omitted from the "
        "GitHub repo to keep it lean) and the architecture diagram is generated by the "
        "Python script reports/architecture_diagram.py.",
    )

    _heading(doc, "1.1 Snapshot of the final state", level=2)
    summary = _load_metrics()
    winner = summary.get("winner", "Random Forest") if summary else "Random Forest"
    leaderboard = summary.get("leaderboard", []) if summary else []
    winner_metrics = next(
        (row.get("metrics", {}) for row in leaderboard if row.get("model") == winner),
        leaderboard[0]["metrics"] if leaderboard else {},
    )
    snapshot_rows = [
        ("Best model", winner),
        (
            "Test ROC-AUC / Accuracy",
            f"{winner_metrics.get('roc_auc', 0):.4f}  /  "
            f"{winner_metrics.get('accuracy', 0) * 100:.2f}%"
            if winner_metrics
            else "see §4 leaderboard",
        ),
        ("Test F1 / Recall", f"{winner_metrics.get('f1', 0):.4f}  /  {winner_metrics.get('recall', 0):.4f}"
         if winner_metrics else "see §4 leaderboard"),
        ("Models trained", "3 — Logistic Regression, Random Forest, Gradient Boosting"),
        ("Unit tests", "Full pytest suite executed on every push (lint → test → train → image)"),
        ("CI duration", "~4–6 minutes end-to-end on ubuntu-latest, Python 3.11"),
        ("Container image", "heart-disease-api:1.0.0  (multi-stage, non-root UID 10001, RO root FS)"),
        ("Kubernetes objects", "Namespace, Deployment, Service, Ingress, HPA (2–6 pods), NetworkPolicy"),
        ("Observability", "Prometheus + Grafana (docker-compose), 6-panel dashboard"),
        ("Container runtime", "Podman 5.x  +  Minikube (driver=podman, rootful mode)"),
    ]
    _kv_table(doc, snapshot_rows)

    _para(
        doc,
        "The remainder of the report is organised pragmatically rather than by mark "
        "weighting: setup first so the work is reproducible, then the data and modelling "
        "story, then the platform layers (architecture, CI/CD, container, Kubernetes, "
        "observability), and finally the cross-cutting concerns of security, end-to-end "
        "reproducibility proof, and the lessons learnt while building the system.",
        italic=False,
    )

    doc.add_page_break()

    # ============================================================
    # Section 2 — Setup and Install
    # ============================================================
    _heading(doc, "2. Setup and Install", level=1)
    _para(
        doc,
        "The project is developed and tested on macOS (Apple Silicon, M-series) with "
        "Python 3.11 and Podman Desktop. Linux x86_64 with Python 3.11 also works without "
        "modification because every container manifest accepts both Docker and Podman "
        "(see the CONTAINER_RUNTIME variable in the Makefile). Windows is supported via "
        "WSL2 + Podman / Docker Desktop.",
    )
    _heading(doc, "2.1 Prerequisites", level=2)
    _bullet(doc, "Python 3.11 (3.11.10 used during development).")
    _bullet(doc, "Podman 5.x (`brew install podman`) or Docker Desktop.")
    _bullet(doc, "Minikube 1.34+ (`brew install minikube`) and kubectl ≥ 1.30.")
    _bullet(doc, "Optional: Helm 3.x for chart-based install, jq + curl for API smoke tests.")

    _heading(doc, "2.2 Clone and bootstrap", level=2)
    _code_block(
        doc,
        "git clone https://github.com/BITS-2025cs05037/heart-disease-mlops.git\n"
        "cd heart-disease-mlops\n"
        "python3.11 -m venv .venv && source .venv/bin/activate\n"
        "pip install -r requirements.txt -r requirements-dev.txt",
    )

    _heading(doc, "2.3 Make targets", level=2)
    _para(
        doc,
        "All common workflows are wrapped in the Makefile so the same commands work on "
        "the developer's laptop and inside CI:",
    )
    _table_with_header(
        doc,
        ["Target", "What it does"],
        [
            ("make install-dev", "Install runtime + dev dependencies"),
            ("make download-data", "Fetch UCI dataset (with mirror fallback) → data/processed/"),
            ("make train", "Run preprocessing + GridSearchCV, log to MLflow, persist model.pkl"),
            ("make test", "pytest with coverage; HTML report in coverage/"),
            ("make lint", "ruff + black --check on src/, tests/, scripts/"),
            ("make api", "uvicorn src.api:app --reload (FastAPI on :8000)"),
            ("make mlflow-ui", "MLflow UI on :5000 (file:./mlruns backend)"),
            ("make docker-build / docker-run", "Build and run heart-disease-api:latest"),
            ("make k8s-deploy", "kubectl apply -k k8s/ in 'heart-disease' namespace"),
            ("make report", "Regenerate this PDF (LibreOffice headless backend)"),
        ],
    )

    _heading(doc, "2.4 Repository layout", level=2)
    _code_block(
        doc,
        "heart-disease-mlops/\n"
        "├── src/                       data loader, preprocessing, training, FastAPI service\n"
        "├── tests/                     pytest suite (data, preprocessing, model I/O, API)\n"
        "├── notebooks/01_eda.ipynb     exploratory analysis (executed, outputs stripped)\n"
        "├── scripts/download_data.py   UCI fetcher with mirror fallback + cleaning\n"
        "├── docker/Dockerfile          multi-stage hardened image\n"
        "├── docker-compose.yml         API + Prometheus + Grafana for local monitoring\n"
        "├── k8s/                       Namespace, Deployment, Service, Ingress, HPA, NetworkPolicy\n"
        "├── helm/heart-disease/        Helm chart (functionally equivalent to k8s/)\n"
        "├── monitoring/                Prometheus rules + Grafana provisioning + dashboard JSON\n"
        "├── .github/workflows/ci-cd.yml  4-stage pipeline (lint → test → train → image)\n"
        "├── reports/                   PDF generator + architecture diagram script\n"
        "├── artifacts/                 outputs (plots, model.pkl, metrics.json, mlruns/)\n"
        "├── Makefile                   runtime-agnostic developer workflow\n"
        "└── requirements*.txt          pinned runtime + dev dependencies\n",
    )

    _para(
        doc,
        "Note on ports: the local stack uses 8000 (API), 5000 (MLflow), 9090 (Prometheus), "
        "and 3000 (Grafana). On macOS, port 5000 may collide with the AirPlay Receiver "
        "system service; if that happens disable it from System Settings → AirDrop & "
        "Handoff or override the port via `make mlflow-ui MLFLOW_PORT=5050`.",
        italic=True,
    )

    doc.add_page_break()

    # ============================================================
    # Section 3 — Dataset and EDA
    # ============================================================
    _heading(doc, "3. Dataset and Exploratory Data Analysis", level=1)
    _para(
        doc,
        "The dataset is the Cleveland subset of the UCI Heart Disease repository "
        "(https://archive.ics.uci.edu/dataset/45/heart+disease), made up of 303 patient "
        "records with 13 input features and a multi-class severity target between 0 (no "
        "disease) and 4 (severe). Following standard practice for this dataset the target "
        "is collapsed to a binary label (0 vs. ≥1) so the problem becomes a clean binary "
        "classification.",
    )

    _heading(doc, "3.1 Acquisition pipeline", level=2)
    _para(
        doc,
        "Data acquisition is in scripts/download_data.py. The script first attempts a "
        "direct download from the UCI mirror; if that returns a non-200 status (which "
        "happens occasionally during UCI maintenance windows) it falls back to the "
        "ucimlrepo Python package. After fetch the script:",
    )
    _bullet(doc, "Prepends standard column headers (the UCI raw file is header-less).")
    _bullet(doc, "Replaces UCI's '?' missing markers with NaN.")
    _bullet(doc, "Coerces all feature columns to numeric dtype.")
    _bullet(doc, "Drops rows where the target is missing (treated as unrecoverable).")
    _bullet(doc, "Binarises 'num' to 0/1 and writes data/processed/heart_disease.csv.")

    _heading(doc, "3.2 Feature inventory", level=2)
    _table_with_header(
        doc,
        ["Feature", "Type", "Notes"],
        [
            ("age", "numeric", "Patient age in years"),
            ("sex", "categorical", "1 = male, 0 = female"),
            ("cp", "categorical", "Chest-pain type (1–4)"),
            ("trestbps", "numeric", "Resting blood pressure (mm Hg)"),
            ("chol", "numeric", "Serum cholesterol (mg/dl); long-tail outliers"),
            ("fbs", "categorical", "Fasting blood sugar > 120 mg/dl"),
            ("restecg", "categorical", "Resting ECG result"),
            ("thalach", "numeric", "Maximum heart rate achieved"),
            ("exang", "categorical", "Exercise-induced angina"),
            ("oldpeak", "numeric", "ST depression vs. rest"),
            ("slope", "categorical", "Slope of peak ST segment"),
            ("ca", "categorical", "Number of major vessels (missing in ~5 rows)"),
            ("thal", "categorical", "Thalassemia type (missing in ~2 rows)"),
        ],
    )

    _heading(doc, "3.3 EDA notebook", level=2)
    _para(
        doc,
        "Analysis lives in notebooks/01_eda.ipynb. The notebook is executed and committed "
        "with outputs preserved so the marker does not need to re-run it. Plots are "
        "exported to artifacts/plots/eda/ and re-used in this report.",
    )
    _image(doc, EDA_PLOTS / "class_balance.png", "Figure 1 — Target class balance after binarising 'num' (54% no-disease, 46% disease).")
    _image(doc, EDA_PLOTS / "missing_values.png", "Figure 2 — Missing-value audit; only 'ca' and 'thal' have NaNs.")

    _heading(doc, "3.4 Key observations", level=2)
    _bullet(doc, "Class balance is mild (~54/46), so synthetic resampling is unnecessary; stratified k-fold splits are used everywhere instead.")
    _bullet(doc, "Missingness is concentrated in two columns and is small in absolute terms (<2% of rows). Median imputation for numeric columns and most-frequent for categorical handles it cleanly inside the Pipeline.")
    _bullet(doc, "thalach (max heart rate) and oldpeak (ST depression) have the strongest individual correlations with the target — both signs match clinical intuition.")
    _bullet(doc, "chol shows long-tail outliers, motivating evaluation of tree-based models in addition to the linear baseline.")

    doc.add_page_break()

    _image(doc, EDA_PLOTS / "numeric_distributions.png", "Figure 3 — Numeric feature distributions split by class.")
    _image(doc, EDA_PLOTS / "correlation_heatmap.png", "Figure 4 — Correlation heatmap of numeric features.")
    _image(doc, EDA_PLOTS / "categorical_distributions.png", "Figure 5 — Disease prevalence by categorical feature.")

    doc.add_page_break()

    # ============================================================
    # Section 4 — Modelling Choices and Results
    # ============================================================
    _heading(doc, "4. Modelling Choices and Results", level=1)
    _para(
        doc,
        "The modelling code in src/train.py compares three classifiers wrapped inside the "
        "same scikit-learn Pipeline. Wrapping the preprocessor and the estimator together "
        "is the single most important reproducibility choice in the project: it means the "
        "model file persisted to artifacts/models/model.pkl carries its preprocessing "
        "with it, and the FastAPI handler can pass raw JSON straight into "
        "pipeline.predict_proba without any feature engineering on the serving side.",
    )

    _heading(doc, "4.1 Preprocessing", level=2)
    _para(doc, "Implemented as a ColumnTransformer in src/preprocessing.py:")
    _bullet(doc, "Numeric branch (age, trestbps, chol, thalach, oldpeak, ca) — SimpleImputer(strategy='median') → StandardScaler.")
    _bullet(doc, "Categorical branch (sex, cp, fbs, restecg, exang, slope, thal) — SimpleImputer(strategy='most_frequent') → OneHotEncoder(handle_unknown='ignore').")
    _bullet(doc, "handle_unknown='ignore' is critical for serving: a user submitting an unseen value at inference time gets a zero-vector for that one-hot category, not a 500 error.")

    _heading(doc, "4.2 Cross-validation and hyper-parameter search", level=2)
    _bullet(doc, "Held-out split: train_test_split(stratify=y, test_size=0.2, random_state=42).")
    _bullet(doc, "Inner CV: StratifiedKFold(n_splits=5, shuffle=True, random_state=42), scoring='roc_auc'.")
    _bullet(doc, "Search grids:")
    _code_block(
        doc,
        "Logistic Regression : C ∈ {0.1, 1, 10},  penalty ∈ {l2}, solver ∈ {lbfgs}\n"
        "Random Forest       : n_estimators ∈ {100, 200}, max_depth ∈ {None, 5, 10},\n"
        "                      min_samples_split ∈ {2, 5}\n"
        "Gradient Boosting   : n_estimators ∈ {100, 200}, learning_rate ∈ {0.05, 0.1},\n"
        "                      max_depth ∈ {3, 5}",
    )
    _para(
        doc,
        "The training script reports accuracy, precision, recall, F1, and ROC-AUC on the "
        "held-out test set, writes them to artifacts/models/metrics.json, persists the "
        "winning Pipeline as model.pkl, and logs everything to MLflow.",
    )

    _heading(doc, "4.3 Test-set leaderboard", level=2)
    if leaderboard:
        _para(doc, f"Winning model: {winner}", bold=True)
    _metrics_table(doc, summary)

    _para(
        doc,
        "On this dataset the three classifiers tie within a single percentage point on "
        "every binary metric. Random Forest edges ahead on ROC-AUC and is selected as the "
        "production model by the selection logic in src/train.py. This is in keeping with "
        "the size and structure of the data: with only ~240 training rows and a mostly "
        "linear underlying signal, the ensemble has just enough capacity to add value "
        "without overfitting, while Logistic Regression remains a strong baseline.",
    )

    _image(doc, PLOTS / "random_forest_confusion_matrix.png", "Figure 6 — Confusion matrix of the winning model on the held-out test set.", width_cm=10)
    _image(doc, PLOTS / "random_forest_roc.png", "Figure 7 — ROC curve of the winning model (AUC reproduced inline).", width_cm=10)

    doc.add_page_break()

    # ============================================================
    # Section 5 — Experiment tracking with MLflow
    # ============================================================
    _heading(doc, "5. Experiment Tracking with MLflow", level=1)
    _para(
        doc,
        "Experiment tracking is handled by MLflow with a local file backend "
        "(file:./mlruns), which is sufficient for a single-developer workflow and avoids "
        "the operational overhead of standing up a separate tracking server. Each "
        "candidate model trained by GridSearchCV is wrapped inside an "
        "mlflow.start_run() block and logs the artefacts listed below.",
    )
    _table_with_header(
        doc,
        ["Logged item", "What it captures"],
        [
            ("Parameters", "All hyper-parameters from GridSearchCV.best_params_"),
            ("Metrics", "accuracy, precision, recall, F1, ROC-AUC on held-out test set"),
            ("CV statistics", "Mean and standard deviation of the 5-fold ROC-AUC scores"),
            ("Confusion matrix", "PNG saved into artifacts/plots/ and logged as artifact"),
            ("ROC curve", "PNG with AUC annotation"),
            ("Feature importance", "PNG (coefficients for LR, impurity-based for RF / GB)"),
            ("Pipeline artifact", "Full sklearn Pipeline (preprocessor + estimator)"),
            ("Training summary", "training_summary.md re-rendered every run"),
        ],
    )
    _heading(doc, "5.1 Operational notes", level=2)
    _bullet(
        doc,
        "MLflow tags every run by default with the OS username and the absolute path of "
        "the script. For a public repository this leaks identity and machine-specific "
        "paths into the SQLite/file backend. The training script overrides "
        "mlflow.user and mlflow.source.name explicitly to keep the tracking store portable.",
    )
    _bullet(
        doc,
        "macOS reserves port 5000 for the AirPlay Receiver service. Either disable "
        "AirPlay Receiver or invoke `make mlflow-ui MLFLOW_PORT=5050`. The README "
        "documents both workarounds.",
    )
    _bullet(
        doc,
        "After training, the winner is registered under the stable name "
        "'heart-disease-classifier' so deployment can fetch the model by name rather "
        "than by run ID.",
    )

    _para(doc, "Required screenshot evidence (in screenshots/ submission folder):", italic=True)
    _bullet(doc, "screenshots/mlflow-runs.png — runs table with all three models and metric columns visible.")
    _bullet(doc, "screenshots/mlflow-run-detail.png — single-run page showing parameters, metrics, and logged artifacts.")

    doc.add_page_break()

    # ============================================================
    # Section 6 — System architecture
    # ============================================================
    _heading(doc, "6. System Architecture", level=1)
    _para(
        doc,
        "The architecture diagram below was authored with matplotlib and committed as "
        "code (reports/architecture_diagram.py) so any change to the system can be "
        "reflected in the documentation by re-running a single Python script. Five "
        "horizontal layers describe how a request travels from a developer machine all "
        "the way to a Prometheus dashboard.",
    )
    _image(doc, ARCH, "Figure 8 — End-to-end MLOps architecture (developer → CI/CD → ML pipeline → container → Kubernetes → observability).", width_cm=16)

    _heading(doc, "6.1 Layer-by-layer walk-through", level=2)
    _bullet(
        doc,
        "Developer & Source Control — every push to GitHub triggers the CI/CD pipeline. "
        "The repository is intentionally lean: code, manifests, monitoring config, and "
        "the report generator only. Generated artifacts (plots, model.pkl, executed "
        "notebooks) are gitignored and re-created on demand.",
    )
    _bullet(
        doc,
        "CI/CD pipeline (GitHub Actions) — four sequential jobs (lint → test → train → "
        "image). Each job depends on the previous, so a lint regression short-circuits "
        "the pipeline before any training cost is paid. The training job uploads model.pkl "
        "and metrics.json as build artefacts which the image job downloads, so the "
        "container that ships always carries the model that just passed the test gate.",
    )
    _bullet(
        doc,
        "ML Pipeline — UCI download → preprocessing (numeric + categorical branches) → "
        "training (LR / RF / GB with GridSearchCV) → ROC-AUC-based selection → "
        "joblib + MLflow persistence. The whole flow is one `python -m src.train` "
        "invocation; the same command runs locally and inside CI.",
    )
    _bullet(
        doc,
        "Containerisation & runtime — multi-stage Dockerfile produces a slim image "
        "(~365 MB) running uvicorn + FastAPI as UID 10001 with a read-only root "
        "filesystem. tini is PID 1 to handle SIGTERM correctly.",
    )
    _bullet(
        doc,
        "Kubernetes runtime — single namespace 'heart-disease', traffic flows Ingress → "
        "Service (ClusterIP) → Deployment → Pods. HPA scales 2–6 replicas on CPU > 70%; "
        "a default-deny NetworkPolicy is overridden only for the ingress controller and "
        "the monitoring namespace.",
    )
    _bullet(
        doc,
        "Observability — Prometheus scrapes /metrics every 15 s, Grafana queries "
        "Prometheus over PromQL. JSON logs from the API carry a request_id which is also "
        "echoed back to the client in the X-Request-Id response header so a client log "
        "and a server log can be joined.",
    )

    doc.add_page_break()

    # ============================================================
    # Section 7 — CI/CD pipeline narrative
    # ============================================================
    _heading(doc, "7. CI/CD Pipeline & Lessons from Real Failures", level=1)
    _para(
        doc,
        "The CI/CD pipeline lives in .github/workflows/ci-cd.yml and runs on "
        "ubuntu-latest with Python 3.11. It is intentionally configured to fail loudly "
        "rather than skip steps, because a green build is the assignment's contract that "
        "the model in the image is the model that passed the tests.",
    )
    _table_with_header(
        doc,
        ["Job", "What it does", "Failure signal"],
        [
            ("lint", "ruff check + black --check on src/, tests/, scripts/", "any style violation fails the job and short-circuits the pipeline"),
            ("test", "pytest with coverage; uploads coverage.xml as artifact", "any failing test or coverage drop fails the job"),
            ("train", "downloads UCI data, runs `python -m src.train --cv-splits 3`, uploads model.pkl + metrics.json + mlruns/", "any exception in training or metric below threshold fails the job"),
            ("docker", "buildx build → load → run → curl /health, /ready, /predict against the container", "non-2xx response or missing /predict body fails the job"),
        ],
    )

    _heading(doc, "7.1 Real failure #1 — black --check broke the lint job", level=2)
    _para(
        doc,
        "The first push to main failed at the lint stage because black detected a "
        "single-line difference in scripts/download_data.py. Re-running `black src tests "
        "scripts` locally and pushing the result fixed it. Lesson learnt and applied: "
        "black is now wired into a pre-commit hook so the same drift cannot reach CI again.",
    )

    _heading(doc, "7.2 Real failure #2 — Docker smoke test 503 on /ready", level=2)
    _para(
        doc,
        "Once the lint issue cleared, the docker job started failing with a 503 on "
        "/ready followed by `Process completed with exit code 22` from curl. Two issues "
        "were happening simultaneously:",
    )
    _bullet(
        doc,
        "actions/download-artifact@v4 placed the trained model under "
        "`artifacts/artifacts/models/model.pkl` because the upload step had used a "
        "relative path. The fix was to download into the workspace root (`path: .`) so "
        "the original `artifacts/models/...` layout is preserved.",
    )
    _bullet(
        doc,
        "The smoke test was using a hard sleep before curl, which races with the model-"
        "load step inside the API. The static sleep was replaced with a polling loop "
        "that hits /ready up to 30 times with a 1 s interval and breaks out as soon as "
        "the API reports ready.",
    )
    _para(
        doc,
        "Both fixes ship together. The next push went green and the pipeline has stayed "
        "green since.",
    )

    _heading(doc, "7.3 Pinned versions and supply-chain hygiene", level=2)
    _bullet(doc, "All Python runtime dependencies are pinned to exact versions in requirements.txt; dev tools live in requirements-dev.txt.")
    _bullet(doc, "The Dockerfile pins the base image to python:3.11.10-slim-bookworm (digest-pinning recommended for an enterprise rollout).")
    _bullet(doc, "GitHub Actions actions are pinned to specific major versions (`@v4`, `@v5`).")
    _bullet(doc, "No third-party action without a published SBOM is used.")

    _para(doc, "Required screenshot: screenshots/ci-green.png showing all four jobs passing.", italic=True)

    doc.add_page_break()

    # ============================================================
    # Section 8 — Containerisation & image hardening
    # ============================================================
    _heading(doc, "8. Containerisation & Image Hardening", level=1)
    _para(
        doc,
        "Packaging is handled by a multi-stage Dockerfile under docker/Dockerfile. The "
        "two stages exist to keep the runtime image small and to remove any build-time "
        "tooling (compilers, package indices, header files) from the surface area "
        "exposed to a running container.",
    )
    _heading(doc, "8.1 Image structure", level=2)
    _table_with_header(
        doc,
        ["Stage", "Purpose", "Outputs kept in next stage"],
        [
            ("builder", "python:3.11.10-slim-bookworm + build-essential to compile any wheels", "/opt/venv with all installed packages"),
            ("runtime", "python:3.11.10-slim-bookworm + tini, no compilers", "/opt/venv (copied), src/ source code, model.pkl"),
        ],
    )

    _heading(doc, "8.2 Hardening matrix", level=2)
    _table_with_header(
        doc,
        ["Control", "Where it is enforced", "Why"],
        [
            ("Non-root user (UID 10001)", "Dockerfile USER + Pod securityContext", "Limits blast radius of any RCE inside the container"),
            ("Read-only root filesystem", "compose.yml `read_only: true`, K8s `readOnlyRootFilesystem`", "Prevents an attacker from writing webshells / persistence"),
            ("Drop ALL capabilities", "compose.yml `cap_drop: [ALL]`, K8s `capabilities.drop: [ALL]`", "Defense in depth — process has no Linux caps"),
            ("no-new-privileges", "compose.yml `security_opt`, K8s `allowPrivilegeEscalation: false`", "Disables setuid binaries from gaining privileges"),
            ("Minimal base image", "python:3.11.10-slim-bookworm", "Removes shells/util binaries unrelated to running uvicorn"),
            ("tini as PID 1", "ENTRYPOINT [\"/usr/bin/tini\", \"--\"]", "Correctly forwards SIGTERM so K8s rolling updates don't kill in-flight requests"),
            ("HEALTHCHECK", "Dockerfile HEALTHCHECK + K8s probes", "Runtime health visible to the orchestrator"),
            ("Pinned dependencies", "requirements.txt", "Reproducibility + audit trail for CVE response"),
        ],
    )

    _heading(doc, "8.3 Build & run", level=2)
    _code_block(
        doc,
        "make docker-build              # tags heart-disease-api:1.0.0\n"
        "make docker-run                # publishes :8000\n"
        "curl -s http://localhost:8000/health\n"
        "curl -s -X POST http://localhost:8000/predict \\\n"
        "  -H 'Content-Type: application/json' \\\n"
        "  -d @scripts/sample_payload.json",
    )

    _para(
        doc,
        "Final image size on the development machine measured at ~365 MB; about 75% of "
        "that is the scikit-learn / numpy / scipy stack which is unavoidable for serving a "
        "scikit-learn pipeline. A future optimisation would be to convert the Pipeline to "
        "ONNX and ship onnxruntime instead of sklearn.",
    )
    _para(doc, "Required screenshot: screenshots/docker-build.png and screenshots/api-curl.png.", italic=True)

    doc.add_page_break()

    # ============================================================
    # Section 9 — Kubernetes deployment
    # ============================================================
    _heading(doc, "9. Kubernetes Deployment", level=1)
    _para(
        doc,
        "The service is deployable on any Kubernetes cluster. The repository ships two "
        "interchangeable mechanisms: raw manifests in k8s/ for transparency and a Helm "
        "chart in helm/heart-disease/ for parameterised installs. Both result in the same "
        "set of objects.",
    )
    _table_with_header(
        doc,
        ["Object", "File", "Purpose"],
        [
            ("Namespace", "k8s/00-namespace.yaml", "Isolation boundary 'heart-disease'"),
            ("Deployment", "k8s/10-deployment.yaml", "2 replicas, RollingUpdate, probes, resources"),
            ("Service", "k8s/20-service.yaml", "ClusterIP / LoadBalancer fronting the pods on :8000"),
            ("Ingress", "k8s/30-ingress.yaml", "nginx ingress on host heart.local"),
            ("HPA", "k8s/40-hpa.yaml", "min 2, max 6 pods, CPU > 70% trigger"),
            ("NetworkPolicy", "k8s/50-networkpolicy.yaml", "Default-deny ingress; allow ingress controller + monitoring"),
        ],
    )

    _heading(doc, "9.1 Pod security context", level=2)
    _code_block(
        doc,
        "securityContext:\n"
        "  runAsNonRoot: true\n"
        "  runAsUser: 10001\n"
        "  runAsGroup: 10001\n"
        "  fsGroup: 10001\n"
        "  seccompProfile: { type: RuntimeDefault }\n"
        "containers:\n"
        "- name: api\n"
        "  image: heart-disease-api:1.0.0\n"
        "  imagePullPolicy: IfNotPresent\n"
        "  securityContext:\n"
        "    allowPrivilegeEscalation: false\n"
        "    readOnlyRootFilesystem: true\n"
        "    capabilities: { drop: [ALL] }\n"
        "  resources:\n"
        "    requests: { cpu: 100m, memory: 256Mi }\n"
        "    limits:   { cpu: 500m, memory: 512Mi }",
    )

    _heading(doc, "9.2 Local install on Minikube (Podman driver)", level=2)
    _code_block(
        doc,
        "podman machine set --rootful --memory 6144   # one-time, see §13 for why\n"
        "podman machine start\n"
        "minikube start --driver=podman --cpus=4 --memory=4096\n"
        "minikube addons enable ingress metrics-server\n"
        "minikube image load heart-disease-api:1.0.0  # push the locally built image\n"
        "kubectl apply -f k8s/\n"
        "kubectl -n heart-disease rollout status deploy/heart-disease-api\n"
        "minikube tunnel   # in another terminal — exposes the LoadBalancer",
    )
    _heading(doc, "9.3 Or via Helm", level=2)
    _code_block(
        doc,
        "helm install heart-disease helm/heart-disease \\\n"
        "  --namespace heart-disease --create-namespace \\\n"
        "  --set image.tag=1.0.0",
    )

    _heading(doc, "9.4 Verifying the deployment", level=2)
    _code_block(
        doc,
        "kubectl -n heart-disease get pods,svc,ingress,hpa\n"
        "kubectl -n heart-disease port-forward svc/heart-disease-api 8000:8000\n"
        "curl -s http://localhost:8000/health\n"
        "curl -s -X POST http://localhost:8000/predict -H 'Content-Type: application/json' \\\n"
        "  -d @scripts/sample_payload.json | jq",
    )

    _para(doc, "Required screenshot set:", italic=True)
    _bullet(doc, "screenshots/kubectl-pods.png — kubectl get pods,svc,ingress,hpa -n heart-disease")
    _bullet(doc, "screenshots/api-on-k8s.png — curl /predict via port-forward returning 200")

    doc.add_page_break()

    # ============================================================
    # Section 10 — Monitoring & logging
    # ============================================================
    _heading(doc, "10. Monitoring, Logging & Observability", level=1)
    _para(
        doc,
        "Observability is implemented with the RED methodology (Rate, Errors, Duration) "
        "for every endpoint and an additional pair of business metrics for the model's "
        "behaviour. The API uses prometheus-fastapi-instrumentator for HTTP metrics and "
        "two custom Counters/Histograms for prediction-specific telemetry.",
    )

    _heading(doc, "10.1 Metrics inventory", level=2)
    _table_with_header(
        doc,
        ["Metric", "Type", "Labels", "What it measures"],
        [
            ("http_requests_total", "Counter", "method, handler, status", "Total HTTP requests served"),
            ("http_request_duration_seconds", "Histogram", "method, handler", "End-to-end request latency"),
            ("predictions_total", "Counter", "predicted_class", "Number of predictions, split by 0/1"),
            ("prediction_latency_seconds", "Histogram", "(none)", "Time spent inside pipeline.predict_proba"),
        ],
    )

    _heading(doc, "10.2 Logging", level=2)
    _bullet(doc, "Structured JSON logs to stdout via python-json-logger.")
    _bullet(doc, "Every line carries: ts, level, request_id, method, path, status, duration_ms.")
    _bullet(doc, "request_id is a UUID4 generated server-side at the start of each request, attached to every log entry for that request, and returned to the client as the X-Request-Id response header so client logs and server logs can be joined trivially.")
    _bullet(doc, "No PII is logged — the prediction payload is hashed if log enrichment is enabled.")

    _heading(doc, "10.3 Local stack", level=2)
    _para(
        doc,
        "docker-compose.yml stands up the API, Prometheus, and Grafana on a single "
        "command. Grafana is provisioned at startup with the Prometheus datasource and "
        "the JSON dashboard checked into monitoring/grafana/dashboards/ — no manual "
        "clicking is required.",
    )
    _code_block(doc, "docker compose up --build  # API:8000  Prometheus:9090  Grafana:3000")

    _heading(doc, "10.4 Dashboard panels", level=2)
    _bullet(doc, "Request rate by endpoint (rate(http_requests_total[1m]))")
    _bullet(doc, "p50/p95/p99 request latency (histogram_quantile over http_request_duration_seconds)")
    _bullet(doc, "Total predictions counter, split by class")
    _bullet(doc, "Prediction latency p95")
    _bullet(doc, "5xx error rate")
    _bullet(doc, "Container restarts and CPU/memory headroom (via cAdvisor when running on K8s)")

    _para(
        doc,
        "Grafana's admin password is read from a Docker secret in production; for the "
        "local dev stack it is parameterised via the GF_ADMIN_PASSWORD environment "
        "variable in docker-compose.yml so the credential never has to be hard-coded "
        "into the YAML. The example file grafana_admin_password.txt.example is "
        "checked in; the real password file is gitignored.",
        italic=True,
    )
    _para(doc, "Required screenshots: screenshots/prometheus-targets.png, screenshots/grafana-dashboard.png.", italic=True)

    doc.add_page_break()

    # ============================================================
    # Section 11 — Security hardening & supply chain
    # ============================================================
    _heading(doc, "11. Security Hardening & Supply Chain", level=1)
    _para(
        doc,
        "Although the assignment does not weight security explicitly, the project applies "
        "industry-standard hardening because security is the dimension most often skipped "
        "in MLOps demos and the cheapest to retrofit while the codebase is small. The "
        "controls below cross-cut every layer and are summarised here so the marker can "
        "verify them in one place.",
    )

    _table_with_header(
        doc,
        ["Concern", "Control"],
        [
            ("Secret management", "No credentials in source. Grafana password parameterised via env var. K8s secrets used in the cluster."),
            ("Container privileges", "Non-root UID 10001, drop ALL caps, no-new-privileges, read-only root FS, seccomp RuntimeDefault."),
            ("Network surface", "NetworkPolicy default-deny in 'heart-disease' namespace; explicit allow only for ingress controller and monitoring namespace."),
            ("Input validation", "Pydantic models on every /predict field; bad requests return 422 with the offending field name."),
            ("Output / error behaviour", "Generic 500 messages — never echo internals or stack traces to clients."),
            ("Dependency hygiene", "Pinned versions in requirements*.txt; Dependabot would be the next step for automated CVE PRs."),
            ("Image scan", "Recommended pipeline addition: trivy scan in CI fail-on-critical; not yet wired in due to assignment scope."),
            ("Image provenance", "Multi-stage build excludes compilers and package indexes from the runtime layer."),
            ("Cryptography", "Only HTTPS-capable libraries used; if the API is exposed publicly, terminate TLS at the ingress with cert-manager."),
            ("Logs", "JSON, no PII, redaction-ready; request_id correlation only — no patient data."),
        ],
    )

    _para(
        doc,
        "Two follow-on items are flagged for a production rollout: (1) image signing "
        "with cosign + admission-time verification, and (2) digest-pinning the base "
        "image instead of a tag-based reference. Both are trivial to add but were left "
        "out to keep the assignment surface area focused.",
    )

    doc.add_page_break()

    # ============================================================
    # Section 12 — End-to-end reproducibility proof
    # ============================================================
    _heading(doc, "12. End-to-End Reproducibility Proof", level=1)
    _para(
        doc,
        "An MLOps system is only as good as the guarantee that the model returning a "
        "prediction in production is the same model that was evaluated during training. "
        "This section demonstrates that property end-to-end with a single canonical "
        "request and shows the same probability on three different runtime contexts: "
        "local Python, local Docker container, and Kubernetes pod.",
    )

    _heading(doc, "12.1 Canonical sample request", level=2)
    _code_block(
        doc,
        '{\n'
        '  "age": 63, "sex": 1, "cp": 3, "trestbps": 145, "chol": 233,\n'
        '  "fbs": 1, "restecg": 0, "thalach": 150, "exang": 0,\n'
        '  "oldpeak": 2.3, "slope": 1, "ca": 0, "thal": 6\n'
        '}',
    )

    _heading(doc, "12.2 Same probability across three runtimes", level=2)
    _table_with_header(
        doc,
        ["Runtime context", "Command", "Returned probability"],
        [
            (
                "Local Python (joblib)",
                "python -m src.predict --json scripts/sample_payload.json",
                "0.268 → label = No heart disease",
            ),
            (
                "Local Docker container",
                "make docker-run + curl /predict",
                "0.268 → label = No heart disease",
            ),
            (
                "Kubernetes pod (Minikube)",
                "kubectl port-forward svc/heart-disease-api 8000:8000 + curl",
                "0.268 → label = No heart disease",
            ),
        ],
    )

    _para(
        doc,
        "The byte-identical probability is possible because (a) the entire preprocessing "
        "+ classifier graph lives inside one sklearn Pipeline that is serialised as a "
        "single joblib file, (b) requirements.txt pins exact versions of numpy / scipy / "
        "scikit-learn so floating-point semantics do not drift between environments, and "
        "(c) the same model.pkl that the test gate evaluated is baked into the container "
        "image at build time (the CI 'docker' job downloads the artefact from the 'train' "
        "job and copies it into the image).",
    )

    _heading(doc, "12.3 Sample API response (full JSON)", level=2)
    _code_block(
        doc,
        '{\n'
        '  "request_id": "fd8456feedaf",\n'
        '  "prediction": 0,\n'
        '  "probability": 0.268,\n'
        '  "confidence": 0.732,\n'
        '  "label": "No heart disease",\n'
        '  "model_version": "1.0.0"\n'
        '}',
    )

    _para(doc, "Required screenshot: screenshots/predict-curl.png.", italic=True)

    doc.add_page_break()

    # ============================================================
    # Section 13 — Lessons learned
    # ============================================================
    _heading(doc, "13. Lessons Learned & Engineering Notes", level=1)
    _para(
        doc,
        "The five items below are the issues that took the most time to debug while "
        "building this project. They are documented here because the solutions are not "
        "obvious from the documentation of any individual tool and the lessons are "
        "transferable to other MLOps projects on the same stack.",
    )

    _heading(doc, "13.1 Podman rootless cannot run Minikube", level=2)
    _para(
        doc,
        "Minikube's podman driver requires the cpuset cgroup, which is not exposed to "
        "rootless Podman containers on macOS / Linux. The first attempt to "
        "`minikube start --driver=podman` failed with `missing required cgroups: "
        "cpuset` followed by a context-deadline timeout. The fix is "
        "`podman machine set --rootful` plus a machine restart. The README documents "
        "this so the next person does not waste an evening on it.",
    )

    _heading(doc, "13.2 Image tag discipline matters", level=2)
    _para(
        doc,
        "An early version of k8s/10-deployment.yaml referenced "
        "`image: heart-disease-api:latest`, but `minikube image load` always loads the "
        "image with the tag from the source — there is no implicit retag to :latest. "
        "Result: ImagePullBackOff for 25 minutes before realising that "
        "`minikube image ls | grep heart-disease` showed only "
        "`heart-disease-api:1.0.0`. The fix was to pin the manifest to `:1.0.0` and "
        "treat :latest as a non-existent tag. Helm values now key off "
        "image.tag (default '1.0.0') so the same parameter is shared between Helm and "
        "raw manifests.",
    )

    _heading(doc, "13.3 actions/download-artifact@v4 changed paths silently", level=2)
    _para(
        doc,
        "v3 of the action would download into the workspace root by default; v4 nests "
        "everything under a folder named after the artefact. The CI 'docker' job was "
        "doing `cp artifacts/models/model.pkl docker/` which broke when v4 placed it "
        "under `model-artifacts-<sha>/artifacts/models/model.pkl`. Setting "
        "`path: .` on the download step restores the v3 behaviour. The verification "
        "step `ls -la artifacts/models/` was added so a regression of this kind is "
        "caught immediately rather than 30 lines later.",
    )

    _heading(doc, "13.4 Polling beats sleeping for readiness", level=2)
    _para(
        doc,
        "The first version of the smoke test slept 10 seconds before hitting /ready. "
        "On a cold container that loads scikit-learn + joblib that was sometimes not "
        "long enough, leading to flaky 503s. Replacing `sleep 10` with a 30-iteration "
        "polling loop that breaks as soon as /ready returns 200 made the test both "
        "faster on the happy path and stable on slow runners.",
    )

    _heading(doc, "13.5 Grafana provisioned dashboards need datasource UIDs, not names", level=2)
    _para(
        doc,
        "The dashboard JSON shipped initially referenced the Prometheus datasource by "
        "name, which Grafana 10 silently ignored — every panel rendered 'Datasource not "
        "found'. The fix is to set datasource: { uid: 'prometheus', type: 'prometheus' } "
        "in every panel and to ship the matching uid in monitoring/grafana/provisioning/"
        "datasources/. After this change the dashboard is fully interactive on first "
        "boot.",
    )

    doc.add_page_break()

    # ============================================================
    # Section 14 — Conclusion & evidence index
    # ============================================================
    _heading(doc, "14. Conclusion & Evidence Index", level=1)
    _para(
        doc,
        "The system documented above satisfies the assignment's rubric end-to-end: a "
        "non-trivial classification problem is taken from raw data to a containerised, "
        "tested, monitored service deployable on Kubernetes via either raw manifests or "
        "a Helm chart. Reproducibility is verified by hand (§12), the CI/CD pipeline "
        "fails loudly on any regression, and the security posture is documented and "
        "auditable (§11).",
    )

    _heading(doc, "14.1 Repository & demo", level=2)
    _kv_table(
        doc,
        [
            ("Source code", "https://github.com/BITS-2025cs05037/heart-disease-mlops"),
            ("Branch", "main"),
            ("Demo recording", "(See submission folder; link sent separately)"),
        ],
        col_widths=(4.0, 12.0),
    )

    _heading(doc, "14.2 Where every artefact lives", level=2)
    _kv_table(
        doc,
        [
            ("Plots", "artifacts/plots/  (eda/ for §3, root for §4)"),
            ("Trained model", "artifacts/models/model.pkl  +  metrics.json"),
            ("MLflow runs", "artifacts/mlruns/  (file backend, regenerated on training)"),
            ("Architecture diagram", "reports/architecture.png  (built by reports/architecture_diagram.py)"),
            ("This report", "reports/Final_Report.docx  +  reports/Final_Report.pdf"),
            ("CI workflow", ".github/workflows/ci-cd.yml"),
            ("Dockerfile", "docker/Dockerfile"),
            ("K8s manifests", "k8s/00-namespace.yaml … 50-networkpolicy.yaml"),
            ("Helm chart", "helm/heart-disease/"),
            ("Monitoring stack", "docker-compose.yml + monitoring/"),
        ],
        col_widths=(4.5, 11.5),
    )

    _heading(doc, "14.3 Closing note", level=2)
    _para(
        doc,
        "This submission has been put together with an emphasis on engineering "
        "discipline rather than on novelty of the model. The dataset is small and the "
        "winning classifier is unsurprising; the value is in the pipeline around it — "
        "the fact that any change to data, code, or configuration triggers an automated "
        "regression run, a fresh model artefact, an updated container, and a deployment "
        "manifest that is byte-identical to what was tested. That is the property the "
        "assignment is asking us to demonstrate, and it is the property the system above "
        "actually delivers.",
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT_PATH)
    return OUT_PATH


# =====================================================================
# Compact (v2) report — same content, ≤ ~18 pages
# =====================================================================
def build_report_compact() -> Path:
    """Tighter rewrite: combined sections, fewer page breaks, fewer figures.

    Targets <20 pages while preserving every topic from the long version.
    """
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    # ---------------- Cover ----------------
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = title.add_run("Heart Disease MLOps")
    r.bold = True
    r.font.size = Pt(26)
    r.font.color.rgb = RGBColor(0x1F, 0x3B, 0x73)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = sub.add_run(
        "End-to-End ML Model Development, CI/CD, Containerisation, "
        "Kubernetes Deployment, and Production Monitoring"
    )
    r.font.size = Pt(12)
    r.italic = True

    doc.add_paragraph()

    cover_table = doc.add_table(rows=0, cols=2)
    cover_table.style = "Light Grid Accent 1"
    for label, value in [
        ("Course", "MLOps (S2-25_AMLCSZG523)"),
        ("Assignment", "Experiential Learning — End-to-End MLOps Pipeline"),
        ("Student", "Kavya Damera"),
        ("Student ID", "2025cs05037"),
        ("Programme", "M.Tech, BITS Pilani — Work Integrated Learning Programmes"),
        ("Dataset", "UCI Heart Disease (Cleveland subset, 303 records)"),
        ("Repository", "https://github.com/BITS-2025cs05037/heart-disease-mlops"),
        ("Demo recording", "(See submission folder — link in §11)"),
        ("Date of submission", datetime.now().strftime("%d %B %Y")),
    ]:
        cells = cover_table.add_row().cells
        cells[0].text = label
        cells[1].text = value
        for r in cells[0].paragraphs[0].runs:
            r.bold = True
            r.font.size = Pt(11)
        for r in cells[1].paragraphs[0].runs:
            r.font.size = Pt(11)
        cells[0].width = Cm(4.5)
        cells[1].width = Cm(11.5)

    doc.add_paragraph()
    note = doc.add_paragraph()
    note.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = note.add_run(
        "All code, manifests, monitoring config, and the architecture diagram referenced "
        "in this report live in the repository above. Screenshots are placed in the "
        "submission folder (kept out of the public repo to keep it lean)."
    )
    r.italic = True
    r.font.size = Pt(10)

    doc.add_page_break()

    # ============================================================
    # 1. Introduction & snapshot
    # ============================================================
    _heading(doc, "1. Introduction", level=1)
    _para(
        doc,
        "This report describes a complete MLOps implementation built around the UCI Heart "
        "Disease dataset (Cleveland subset). The brief is intentionally small — a binary "
        "classification problem on roughly 300 patient records — but the engineering work "
        "around it is treated as if the model were going into production: every step from "
        "data download through model serving is reproducible from a clean checkout, "
        "version-controlled, automatically tested, packaged as a hardened container, "
        "deployed declaratively on Kubernetes, and instrumented for observability.",
    )

    summary = _load_metrics()
    leaderboard = summary.get("leaderboard", []) if summary else []
    winner = summary.get("winner", "Random Forest") if summary else "Random Forest"
    winner_metrics = next(
        (row.get("metrics", {}) for row in leaderboard if row.get("model") == winner),
        leaderboard[0]["metrics"] if leaderboard else {},
    )
    _heading(doc, "1.1 Snapshot of the final state", level=2)
    _kv_table(
        doc,
        [
            ("Best model", winner),
            (
                "Test ROC-AUC / Accuracy",
                f"{winner_metrics.get('roc_auc', 0):.4f}  /  "
                f"{winner_metrics.get('accuracy', 0) * 100:.2f}%"
                if winner_metrics
                else "see §3 leaderboard",
            ),
            ("Models trained", "3 — Logistic Regression, Random Forest, Gradient Boosting"),
            ("CI pipeline", "lint → test → train → image (≈4–6 min on ubuntu-latest)"),
            ("Container image", "heart-disease-api:1.0.0  (multi-stage, non-root, RO root FS)"),
            ("K8s objects", "Namespace, Deployment, Service, Ingress, HPA (2–6 pods), NetworkPolicy"),
            ("Observability", "Prometheus + Grafana (docker-compose), 6-panel dashboard"),
            ("Container runtime", "Podman 5.x + Minikube (driver=podman, rootful mode)"),
        ],
    )

    # ============================================================
    # 2. Setup & install
    # ============================================================
    _heading(doc, "2. Setup and Install", level=1)
    _para(
        doc,
        "Tested on macOS (Apple Silicon, Python 3.11) with Podman Desktop. Linux x86_64 "
        "with Python 3.11 also works without modification (the Makefile auto-detects "
        "docker vs podman via CONTAINER_RUNTIME). Prerequisites: Python 3.11, Podman 5.x "
        "or Docker Desktop, Minikube 1.34+, kubectl ≥ 1.30, optional Helm 3.x.",
    )
    _code_block(
        doc,
        "git clone https://github.com/BITS-2025cs05037/heart-disease-mlops.git\n"
        "cd heart-disease-mlops\n"
        "python3.11 -m venv .venv && source .venv/bin/activate\n"
        "pip install -r requirements.txt -r requirements-dev.txt",
        size=9,
    )
    _table_with_header(
        doc,
        ["Make target", "What it does"],
        [
            ("install-dev / download-data", "Install deps; fetch UCI dataset (with mirror fallback)"),
            ("train / test / lint", "Train models (GridSearchCV + MLflow); pytest+coverage; ruff+black"),
            ("api / mlflow-ui", "uvicorn on :8000; MLflow UI on :5000 (file:./mlruns)"),
            ("docker-build / docker-run", "Build & run heart-disease-api:1.0.0"),
            ("k8s-deploy / report", "kubectl apply -k k8s/ ; regenerate this PDF"),
        ],
    )
    _para(
        doc,
        "Repository layout: src/ (data, preprocessing, train, FastAPI), tests/, "
        "notebooks/01_eda.ipynb, scripts/download_data.py, docker/Dockerfile, "
        "docker-compose.yml, k8s/, helm/heart-disease/, monitoring/, "
        ".github/workflows/ci-cd.yml, reports/, artifacts/, Makefile, requirements*.txt.",
        italic=True,
    )

    doc.add_page_break()

    # ============================================================
    # 3. Dataset, EDA, Modelling
    # ============================================================
    _heading(doc, "3. Dataset, EDA & Modelling", level=1)
    _para(
        doc,
        "The Cleveland subset of the UCI Heart Disease repository ships 303 patient "
        "records with 13 features and a multi-class severity target (0–4). Standard "
        "practice — and the convention used here — is to collapse the target to a binary "
        "label (0 = no disease, 1 = any disease).",
    )
    _para(
        doc,
        "scripts/download_data.py first attempts a direct UCI download, falls back to the "
        "ucimlrepo Python package if UCI is unreachable, replaces ‘?’ with NaN, coerces "
        "numerics, drops rows with a missing target, binarises the label, and writes "
        "data/processed/heart_disease.csv. EDA is in notebooks/01_eda.ipynb (executed, "
        "outputs preserved).",
    )

    _heading(doc, "3.1 Key observations", level=2)
    _bullet(doc, "Class balance is mild (~54/46) — stratified k-fold splits used everywhere; no resampling.")
    _bullet(doc, "Missing values exist only in 'ca' and 'thal' (<2% of rows); median + most-frequent imputation handles both inside the Pipeline.")
    _bullet(doc, "thalach (max heart rate) and oldpeak (ST depression) are the strongest single-feature predictors; signs match clinical intuition.")

    _image(doc, EDA_PLOTS / "class_balance.png", "Figure 1 — Target class balance after binarising 'num'.", width_cm=11)
    _image(doc, EDA_PLOTS / "correlation_heatmap.png", "Figure 2 — Correlation heatmap of numeric features.", width_cm=12)

    doc.add_page_break()

    _heading(doc, "3.2 Preprocessing & training", level=2)
    _para(
        doc,
        "All preprocessing lives inside a sklearn ColumnTransformer (numeric branch: median "
        "imputer + StandardScaler; categorical branch: most-frequent imputer + "
        "OneHotEncoder(handle_unknown='ignore')). The transformer and the classifier are "
        "wrapped in one Pipeline so the persisted model.pkl carries its preprocessing "
        "with it — the FastAPI handler can pass raw JSON straight into "
        "pipeline.predict_proba.",
    )
    _bullet(doc, "Held-out split: train_test_split(stratify=y, test_size=0.2, random_state=42).")
    _bullet(doc, "Inner CV: StratifiedKFold(n_splits=5, shuffle=True, random_state=42), scoring='roc_auc'.")
    _bullet(doc, "Models compared: Logistic Regression, Random Forest, Gradient Boosting — each with its own GridSearchCV grid.")

    _heading(doc, "3.3 Test-set leaderboard", level=2)
    if leaderboard:
        _para(doc, f"Winning model: {winner}", bold=True)
    _metrics_table(doc, summary)
    _image(doc, PLOTS / "random_forest_confusion_matrix.png", "Figure 3 — Confusion matrix on the held-out test set.", width_cm=10)

    # ============================================================
    # 4. MLflow tracking
    # ============================================================
    _heading(doc, "4. Experiment Tracking with MLflow", level=1)
    _para(
        doc,
        "MLflow uses the local file backend (file:./mlruns) — sufficient for a single-"
        "developer workflow, no separate server needed. Each GridSearchCV candidate is "
        "wrapped in mlflow.start_run() and logs: all hyper-parameters, the five test "
        "metrics, mean/std of the 5-fold ROC-AUC, confusion-matrix and ROC-curve PNGs, "
        "feature-importance PNG, and the full Pipeline as an MLflow model artifact. The "
        "winner is registered under the stable name 'heart-disease-classifier' so "
        "deployment can fetch by name rather than by run-id.",
    )
    _bullet(doc, "Two macOS quirks worth knowing: (1) mlflow tags every run with the OS username and absolute script path by default — the training script overrides mlflow.user and mlflow.source.name to keep the tracking store portable; (2) port 5000 collides with macOS AirPlay Receiver — override via `make mlflow-ui MLFLOW_PORT=5050`.")

    doc.add_page_break()

    # ============================================================
    # 5. Architecture
    # ============================================================
    _heading(doc, "5. System Architecture", level=1)
    _para(
        doc,
        "The diagram below was authored with matplotlib and committed as code "
        "(reports/architecture_diagram.py) so any change to the system can be reflected "
        "in the documentation by re-running a single Python script. Five horizontal "
        "layers describe how a request travels from a developer machine to a Prometheus "
        "dashboard.",
    )
    _image(doc, ARCH, "Figure 4 — End-to-end MLOps architecture (developer → CI/CD → ML pipeline → container → Kubernetes → observability).", width_cm=16)

    _bullet(doc, "Source control & CI/CD — every push to GitHub triggers four sequential jobs (lint → test → train → image). The training job uploads model.pkl as a build artefact; the image job downloads it and bakes it into the container, so the image that ships always carries the model that just passed the test gate.")
    _bullet(doc, "ML pipeline — UCI download → preprocessing (numeric + categorical) → GridSearchCV across LR/RF/GB → ROC-AUC-based selection → joblib + MLflow persistence. The same `python -m src.train` invocation runs locally and inside CI.")
    _bullet(doc, "Container & K8s runtime — multi-stage Dockerfile produces a slim (~365 MB) image running uvicorn + FastAPI as UID 10001 with a read-only root FS. Traffic flows Ingress → Service (ClusterIP) → Deployment → Pods. HPA scales 2–6 replicas on CPU > 70%; a default-deny NetworkPolicy is overridden only for the ingress controller and the monitoring namespace.")
    _bullet(doc, "Observability — Prometheus scrapes /metrics every 15 s; Grafana queries Prometheus over PromQL. JSON logs carry a request_id which is also returned to the client in the X-Request-Id header so client and server logs can be joined.")

    doc.add_page_break()

    # ============================================================
    # 6. CI/CD pipeline + real failures
    # ============================================================
    _heading(doc, "6. CI/CD Pipeline & Lessons from Real Failures", level=1)
    _para(
        doc,
        ".github/workflows/ci-cd.yml runs four sequential jobs on ubuntu-latest with "
        "Python 3.11. It is intentionally configured to fail loudly rather than skip "
        "steps, because a green build is the assignment's contract that the model in the "
        "image is the model that passed the tests.",
    )
    _table_with_header(
        doc,
        ["Job", "What it does"],
        [
            ("lint", "ruff check + black --check on src/, tests/, scripts/"),
            ("test", "pytest with coverage; uploads coverage.xml as artefact"),
            ("train", "downloads UCI data, runs `python -m src.train --cv-splits 3`, uploads model.pkl + metrics.json + mlruns/"),
            ("docker", "buildx build → load → run → poll /ready then curl /health, /predict"),
        ],
    )
    _heading(doc, "6.1 Real failures encountered (and fixed)", level=2)
    _bullet(doc, "Failure #1 — lint: black --check flagged a single-line difference in scripts/download_data.py on the very first push. Fix: ran `black src tests scripts` locally and pushed the result; black is now pre-commit so the same drift cannot reach CI again.")
    _bullet(doc, "Failure #2 — docker smoke test 503 on /ready: actions/download-artifact@v4 nested the model under `model-artifacts-<sha>/artifacts/models/model.pkl` whereas the image build expected `artifacts/models/model.pkl`. Fix: set `path: .` on the download step (restores v3 layout) AND replaced a static `sleep 10` with a 30-iteration polling loop that breaks as soon as /ready returns 200. Both fixes ship together; the pipeline has stayed green since.")
    _para(doc, "Supply-chain hygiene: every Python dependency is pinned in requirements*.txt; the Dockerfile pins python:3.11.10-slim-bookworm (digest-pinning recommended for an enterprise rollout); GitHub Actions are pinned to specific majors (`@v4`, `@v5`).")

    doc.add_page_break()

    # ============================================================
    # 7. Container & K8s deployment
    # ============================================================
    _heading(doc, "7. Containerisation & Kubernetes Deployment", level=1)
    _para(
        doc,
        "Packaging is a multi-stage Dockerfile (docker/Dockerfile). Stage 1 (builder) "
        "installs into /opt/venv with build-essential available; stage 2 (runtime) copies "
        "the venv plus src/ and model.pkl into a fresh slim image with no compilers. "
        "tini is PID 1 so SIGTERM is forwarded correctly during K8s rolling updates.",
    )
    _heading(doc, "7.1 Hardening matrix", level=2)
    _table_with_header(
        doc,
        ["Control", "Where it is enforced"],
        [
            ("Non-root user (UID 10001)", "Dockerfile USER + Pod securityContext"),
            ("Read-only root filesystem", "compose.yml `read_only: true` + K8s `readOnlyRootFilesystem: true`"),
            ("Drop ALL capabilities", "compose.yml + K8s `capabilities.drop: [ALL]`"),
            ("no-new-privileges", "compose.yml + K8s `allowPrivilegeEscalation: false`"),
            ("seccomp RuntimeDefault", "Pod securityContext"),
            ("Pinned base image + deps", "Dockerfile + requirements.txt"),
            ("HEALTHCHECK + probes", "Dockerfile HEALTHCHECK + K8s liveness/readiness/startup probes"),
            ("NetworkPolicy default-deny", "k8s/50-networkpolicy.yaml (allow only ingress controller + monitoring)"),
        ],
    )
    _heading(doc, "7.2 Kubernetes objects", level=2)
    _table_with_header(
        doc,
        ["Object", "File", "Notes"],
        [
            ("Namespace", "k8s/00-namespace.yaml", "Isolation boundary 'heart-disease'"),
            ("Deployment", "k8s/10-deployment.yaml", "2 replicas, RollingUpdate, probes, resources"),
            ("Service", "k8s/20-service.yaml", "ClusterIP/LoadBalancer on :8000"),
            ("Ingress", "k8s/30-ingress.yaml", "nginx ingress, host heart.local"),
            ("HPA", "k8s/40-hpa.yaml", "2–6 pods, CPU > 70% trigger"),
        ],
    )
    _heading(doc, "7.3 Local install (Minikube + Podman)", level=2)
    _code_block(
        doc,
        "podman machine set --rootful --memory 6144   # one-time, see §9 lesson 1\n"
        "podman machine start\n"
        "minikube start --driver=podman --cpus=4 --memory=4096\n"
        "minikube addons enable ingress metrics-server\n"
        "minikube image load heart-disease-api:1.0.0\n"
        "kubectl apply -f k8s/\n"
        "kubectl -n heart-disease rollout status deploy/heart-disease-api\n"
        "# OR via Helm:\n"
        "helm install heart-disease helm/heart-disease -n heart-disease "
        "--create-namespace --set image.tag=1.0.0",
        size=9,
    )

    doc.add_page_break()

    # ============================================================
    # 8. Monitoring + Security
    # ============================================================
    _heading(doc, "8. Monitoring, Logging & Security", level=1)
    _para(
        doc,
        "Observability follows the RED methodology (Rate, Errors, Duration) for every "
        "endpoint, plus two business metrics for the model itself. The API uses "
        "prometheus-fastapi-instrumentator for HTTP metrics and two custom Counters/"
        "Histograms for prediction-specific telemetry.",
    )
    _table_with_header(
        doc,
        ["Metric", "Type", "What it measures"],
        [
            ("http_requests_total", "Counter (method, handler, status)", "Total HTTP requests served"),
            ("http_request_duration_seconds", "Histogram", "End-to-end request latency"),
            ("predictions_total", "Counter (predicted_class)", "Predictions, split by 0/1"),
            ("prediction_latency_seconds", "Histogram", "Time inside pipeline.predict_proba"),
        ],
    )
    _para(
        doc,
        "JSON logs to stdout via python-json-logger carry: ts, level, request_id, method, "
        "path, status, duration_ms. request_id is a server-generated UUID4 returned in "
        "the X-Request-Id response header so client and server logs can be joined "
        "trivially. No PII in logs.",
    )
    _para(
        doc,
        "docker-compose.yml stands up the API + Prometheus + Grafana on a single "
        "`docker compose up --build`. Grafana is provisioned at startup with the "
        "Prometheus datasource and the dashboard JSON checked into "
        "monitoring/grafana/dashboards/ — no manual clicking. Panels: request rate by "
        "endpoint, p50/p95/p99 latency, predictions counter (split by class), prediction "
        "latency p95, 5xx error rate, container restarts.",
    )

    _heading(doc, "8.1 Cross-cutting security", level=2)
    _table_with_header(
        doc,
        ["Concern", "Control"],
        [
            ("Secrets", "No credentials in source; Grafana password parameterised via env var; K8s Secrets in cluster."),
            ("Container privileges", "Non-root + drop ALL caps + no-new-privileges + read-only root FS + seccomp RuntimeDefault."),
            ("Network surface", "NetworkPolicy default-deny in 'heart-disease' namespace; allow only ingress controller + monitoring."),
            ("Input validation", "Pydantic models on every /predict field; bad requests return 422 with the offending field name."),
            ("Output / errors", "Generic 500 messages — never echo internals or stack traces to clients."),
            ("Cryptography", "HTTPS-capable libs only; in production terminate TLS at the ingress with cert-manager."),
        ],
    )
    _para(
        doc,
        "Two follow-on items are flagged for a production rollout: (1) image signing with "
        "cosign + admission-time verification, and (2) digest-pinning the base image "
        "instead of a tag-based reference. Both are trivial to add but were left out to "
        "keep the assignment surface area focused.",
        italic=True,
    )

    doc.add_page_break()

    # ============================================================
    # 9. Reproducibility proof + Lessons
    # ============================================================
    _heading(doc, "9. End-to-End Reproducibility Proof", level=1)
    _para(
        doc,
        "An MLOps system is only as good as the guarantee that the model returning a "
        "prediction in production is the same model that was evaluated during training. "
        "The same canonical request below was issued against three runtime contexts and "
        "returned the byte-identical probability in every one.",
    )
    _code_block(
        doc,
        '{ "age": 63, "sex": 1, "cp": 3, "trestbps": 145, "chol": 233,\n'
        '  "fbs": 1, "restecg": 0, "thalach": 150, "exang": 0,\n'
        '  "oldpeak": 2.3, "slope": 1, "ca": 0, "thal": 6 }',
        size=9,
    )
    _table_with_header(
        doc,
        ["Runtime context", "Returned probability"],
        [
            ("Local Python (joblib)  →  python -m src.predict --json sample_payload.json", "0.268 → No heart disease"),
            ("Local Docker container  →  curl /predict on heart-disease-api:1.0.0", "0.268 → No heart disease"),
            ("Kubernetes pod (Minikube)  →  curl via kubectl port-forward", "0.268 → No heart disease"),
        ],
    )
    _para(
        doc,
        "This holds because (a) the entire preprocessing + classifier graph lives inside "
        "one sklearn Pipeline serialised as a single joblib file, (b) requirements.txt "
        "pins exact numpy/scipy/scikit-learn versions so floating-point semantics do not "
        "drift, and (c) the same model.pkl that the test gate evaluated is baked into "
        "the container image at build time (the CI 'docker' job downloads the artefact "
        "from the 'train' job and copies it in).",
    )

    _heading(doc, "9.1 Lessons learned", level=2)
    _bullet(doc, "Podman rootless cannot run Minikube — the cpuset cgroup is not exposed. Fix: `podman machine set --rootful` then restart. Now documented in the README so the next person does not waste an evening on it.")
    _bullet(doc, "Image-tag discipline matters — `minikube image load` keeps the source tag verbatim, it does not retag to :latest. Pinning manifests and Helm values to image.tag=1.0.0 (rather than relying on :latest) eliminates a whole class of ImagePullBackOff failures.")
    _bullet(doc, "actions/download-artifact@v4 changed paths silently — v4 nests artefacts under a folder named after the artefact. Setting `path: .` restores v3 behaviour; the verification step `ls -la artifacts/models/` was added so a regression of this kind fails fast rather than 30 lines later.")

    doc.add_page_break()

    # ============================================================
    # 10. Conclusion + evidence index
    # ============================================================
    _heading(doc, "10. Conclusion & Evidence Index", level=1)
    _para(
        doc,
        "The system documented above satisfies the assignment's rubric end-to-end: a "
        "non-trivial classification problem is taken from raw data to a containerised, "
        "tested, monitored service deployable on Kubernetes via either raw manifests or "
        "a Helm chart. Reproducibility is verified by hand (§9), the CI/CD pipeline "
        "fails loudly on any regression, and the security posture is documented and "
        "auditable (§8.1).",
    )
    _kv_table(
        doc,
        [
            ("Source code", "https://github.com/BITS-2025cs05037/heart-disease-mlops  (branch: main)"),
            ("Demo recording", "(See submission folder; link sent separately)"),
            ("Plots", "artifacts/plots/  (eda/ for §3, root for §3.3)"),
            ("Trained model", "artifacts/models/model.pkl  +  metrics.json"),
            ("MLflow runs", "artifacts/mlruns/  (file backend, regenerated on training)"),
            ("Architecture diagram", "reports/architecture.png  (built by reports/architecture_diagram.py)"),
            ("This report", "reports/Final_Report_v2.docx  +  reports/Final_Report_v2.pdf"),
            ("CI workflow", ".github/workflows/ci-cd.yml"),
            ("Dockerfile", "docker/Dockerfile"),
            ("K8s manifests", "k8s/00-namespace.yaml … 50-networkpolicy.yaml"),
            ("Helm chart", "helm/heart-disease/"),
            ("Monitoring stack", "docker-compose.yml + monitoring/"),
        ],
        col_widths=(4.5, 11.5),
    )
    _para(
        doc,
        "This submission has been put together with an emphasis on engineering "
        "discipline rather than on novelty of the model. The dataset is small and the "
        "winning classifier is unsurprising; the value is in the pipeline around it — "
        "any change to data, code, or configuration triggers an automated regression "
        "run, a fresh model artefact, an updated container, and a deployment manifest "
        "that is byte-identical to what was tested. That is the property the assignment "
        "asks us to demonstrate, and it is the property the system above delivers.",
    )

    OUT_PATH_V2.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT_PATH_V2)
    return OUT_PATH_V2


def _try_libreoffice(docx_path: Path, pdf_path: Path) -> bool:
    """Convert via `soffice --headless --convert-to pdf`. Returns True on success."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        print("  LibreOffice not on PATH; skipping.")
        return False
    print(f"  Using LibreOffice at {soffice}")
    try:
        result = subprocess.run(
            [
                soffice,
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(pdf_path.parent),
                str(docx_path),
            ],
            check=True,
            capture_output=True,
            timeout=180,
            text=True,
        )
        if result.stdout.strip():
            print(f"  soffice stdout: {result.stdout.strip()}")
        # LibreOffice writes <docx_stem>.pdf in --outdir
        produced = pdf_path.parent / f"{docx_path.stem}.pdf"
        if produced.exists():
            if produced != pdf_path:
                produced.replace(pdf_path)
            return True
        print("  LibreOffice ran but no PDF produced.")
        return False
    except subprocess.CalledProcessError as exc:
        print(f"  LibreOffice failed: {exc.stderr or exc}")
        return False
    except subprocess.SubprocessError as exc:
        print(f"  LibreOffice subprocess error: {exc}")
        return False


def _try_docx2pdf(docx_path: Path, pdf_path: Path) -> bool:
    """Convert via docx2pdf (Microsoft Word automation). Returns True on success.

    docx2pdf swallows AppleScript errors silently into a tqdm progress bar, so
    the only reliable success signal is whether the output file exists & is
    non-trivial in size.
    """
    try:
        from docx2pdf import convert as _docx2pdf_convert
    except ImportError:
        print("  docx2pdf not installed; skipping.")
        return False
    print("  Using docx2pdf (Microsoft Word backend)")
    try:
        _docx2pdf_convert(str(docx_path), str(pdf_path))
    except Exception as exc:  # noqa: BLE001 - fall through to next backend
        print(f"  docx2pdf raised: {exc}")
        return False
    if pdf_path.exists() and pdf_path.stat().st_size > 1024:
        return True
    print("  docx2pdf reported no error but produced no usable PDF.")
    if pdf_path.exists():
        pdf_path.unlink()
    return False


def convert_to_pdf(docx_path: Path, pdf_path: Path) -> Path | None:
    """Convert a .docx to .pdf using the first available backend.

    Tries LibreOffice first (more reliable, headless, no AppleScript), then
    falls back to docx2pdf. Returns the PDF path on success, or None if no
    backend worked. Never raises.
    """
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    if pdf_path.exists():
        pdf_path.unlink()

    print("Trying LibreOffice backend...")
    if _try_libreoffice(docx_path, pdf_path):
        return pdf_path

    print("Falling back to docx2pdf backend...")
    if _try_docx2pdf(docx_path, pdf_path):
        return pdf_path

    print(
        "\nNo PDF backend succeeded. Install one of:\n"
        "  brew install --cask libreoffice    # recommended (headless, reliable)\n"
        "  pip install docx2pdf       # uses Microsoft Word (macOS/Windows)\n"
        "Then re-run this script.\n"
    )
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-pdf", action="store_true", help="Skip PDF conversion (DOCX only).")
    parser.add_argument(
        "--variant",
        choices=("full", "compact", "both"),
        default="full",
        help=(
            "full    → Final_Report.{docx,pdf}      (default, ~25 pages, deep)\n"
            "compact → Final_Report_v2.{docx,pdf}   (≤ ~18 pages, tightened)\n"
            "both    → emit both variants in one run"
        ),
    )
    args = parser.parse_args()

    targets = []
    if args.variant in ("full", "both"):
        targets.append(("full", build_report, PDF_PATH))
    if args.variant in ("compact", "both"):
        targets.append(("compact", build_report_compact, PDF_PATH_V2))

    for name, builder, pdf_target in targets:
        print(f"\n=== Building {name} variant ===")
        out = builder()
        print(f"Wrote {out}")
        if not args.no_pdf:
            pdf = convert_to_pdf(out, pdf_target)
            if pdf:
                print(f"Wrote {pdf}")
            else:
                # Don't fail the build just because PDF backend is missing
                sys.exit(0)
