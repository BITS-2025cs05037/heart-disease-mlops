# Heart Disease MLOps — End-to-End Production Pipeline

[![CI/CD](https://github.com/BITS-2025cs05037/heart-disease-mlops/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/BITS-2025cs05037/heart-disease-mlops/actions/workflows/ci-cd.yml)

> **MLOps Experiential Learning Assignment — BITS Pilani M.Tech**
> Course: `MLOps (S2-25_AMLCSZG523)` · Total marks: 50

A production-ready machine-learning service that predicts the presence of heart disease from 13 routinely collected clinical features. Every stage — data acquisition, model training, experiment tracking, packaging, automated testing, containerisation, Kubernetes deployment, and monitoring — is automated and reproducible from a clean checkout.

---

## Repository structure

```
heart-disease-mlops/
├── .github/workflows/ci-cd.yml      # GitHub Actions: lint -> test -> train -> docker
├── data/{raw,processed}             # downloaded + cleaned dataset (gitignored)
├── notebooks/01_eda.ipynb           # Task 1: EDA notebook with all visualisations
├── src/
│   ├── data_loader.py               # Canonical schema + stratified train/test
│   ├── preprocessing.py             # ColumnTransformer (impute + encode + scale)
│   ├── train.py                     # Grid-search 3 models, MLflow logging, model registry
│   ├── evaluate.py                  # Metrics + confusion matrix / ROC plotters
│   └── api.py                       # FastAPI: /predict /health /ready /metrics
├── tests/                           # pytest: data, preprocessing, model I/O, API
├── docker/Dockerfile                # multi-stage, non-root, read-only-friendly image
├── k8s/                             # Namespace, Deployment, Service, Ingress, HPA, NetworkPolicy
├── helm/heart-disease/              # Helm chart equivalent
├── monitoring/                      # Prometheus + Grafana provisioning + dashboard JSON
├── reports/
│   ├── architecture_diagram.py      # Renders reports/architecture.png
│   └── generate_report.py           # Renders reports/Final_Report.docx (~10 pages)
├── screenshots/                     # MLflow UI / Grafana / kubectl / API responses
├── scripts/download_data.py         # UCI dataset downloader (idempotent, 2 mirrors)
├── docker-compose.yml               # Local API + Prometheus + Grafana stack
├── Makefile                         # `make install-dev | train | test | api | docker-* | mlflow-ui`
├── requirements.txt                 # Pinned runtime deps
└── requirements-dev.txt             # Pinned dev/test/lint deps
```

---

## Quick start (clean machine)

> Pre-requisites: Python 3.11, a container runtime (**Docker** *or* **Podman**), Minikube, kubectl, Helm.
>
> **With Docker:** `brew install python@3.11 kubectl minikube helm && brew install --cask docker`
>
> **With Podman** (use this if Docker Desktop is not allowed on your machine):
> ```bash
> brew install python@3.11 kubectl minikube helm podman
> brew install --cask podman-desktop
> podman machine init --cpus 4 --memory 4096 --disk-size 30
> podman machine start
> ```

The Makefile auto-detects whichever runtime is on your PATH — every `make` target works unchanged.

```bash
git clone https://github.com/BITS-2025cs05037/heart-disease-mlops.git
cd heart-disease-mlops

make install-dev         # creates .venv, installs all deps
make download-data       # writes data/processed/heart_disease.csv
make train               # trains LR + RF + GBM, logs to MLflow, saves artifacts/models/model.pkl
make test                # runs pytest with coverage
make api                 # starts FastAPI on http://localhost:8000/docs
make mlflow-ui           # MLflow UI on http://localhost:5000

# Container build / run / compose — runtime-agnostic
make container-build     # uses docker if present, else podman
make container-run       # background run on :8000
make container-stop      # stop the running container
make compose-up          # API + Prometheus + Grafana
```

Sample inference call:

```bash
curl -X POST http://localhost:8000/predict \
  -H 'Content-Type: application/json' \
  -d '{"age":63,"sex":1,"cp":3,"trestbps":145,"chol":233,"fbs":1,"restecg":0,"thalach":150,"exang":0,"oldpeak":2.3,"slope":1,"ca":0,"thal":6}'
```

Response:

```json
{
  "request_id": "...",
  "prediction": 1,
  "probability": 0.78,
  "confidence": 0.78,
  "label": "Heart disease",
  "model_version": "1.0.0"
}
```

---

## Local end-to-end stack (API + Prometheus + Grafana)

```bash
make train               # ensure model.pkl exists
make compose-up          # docker compose OR podman compose, auto-detected
```

* API — http://localhost:8000/docs
* Prometheus — http://localhost:9090
* Grafana — http://localhost:3000 (admin / admin) — dashboard auto-provisioned

---

## Kubernetes deployment (Minikube)

### With Docker driver (default)
```bash
minikube start --cpus=4 --memory=4096
minikube addons enable ingress metrics-server
eval $(minikube docker-env)
docker build -f docker/Dockerfile -t heart-disease-api:latest .
kubectl apply -f k8s/
```

### With Podman driver (no Docker required)
```bash
podman machine start
minikube start --driver=podman --cpus=4 --memory=4096 --container-runtime=cri-o
minikube addons enable ingress metrics-server
minikube image build -t heart-disease-api:latest -f docker/Dockerfile .
kubectl apply -f k8s/
```

### Common steps
```bash
kubectl get pods -n heart-disease -w     # wait for 2/2 Ready

# Expose via LoadBalancer (in another terminal)
minikube tunnel
kubectl get svc -n heart-disease
```

Or deploy via Helm:
```bash
helm install heart-disease helm/heart-disease \
  --namespace heart-disease --create-namespace
```

---

## CI/CD

`.github/workflows/ci-cd.yml` runs on every push and PR:

1. **lint** — ruff + black --check
2. **test** — pytest with coverage; report uploaded as artifact
3. **train** — downloads dataset, trains models with `--cv-splits 3`, uploads `model.pkl`, `metrics.json`, MLflow runs, plots
4. **docker** — builds image, smoke-tests `/health`, `/ready`, `/predict`

The pipeline fails fast on lint or test errors and surfaces clear logs.

---

## Marking-rubric mapping

| Task | Marks | Delivered in |
|------|-------|--------------|
| 1. Data Acquisition & EDA | 5 | `scripts/download_data.py`, `notebooks/01_eda.ipynb` |
| 2. Feature engineering & ≥2 models | 8 | `src/preprocessing.py`, `src/train.py` (LR + RF + GBM, GridSearchCV, 5-fold CV, all metrics) |
| 3. Experiment tracking | 5 | MLflow integrated in `src/train.py` (params, metrics, plots, registered model) |
| 4. Packaging & reproducibility | 7 | `requirements*.txt`, sklearn Pipeline, `joblib.dump`, MLflow model |
| 5. CI/CD + automated testing | 8 | `tests/`, `.github/workflows/ci-cd.yml` (lint → test → train → docker) |
| 6. Containerisation | 5 | `docker/Dockerfile` (multi-stage, non-root), `docker-compose.yml` |
| 7. Production deployment | 7 | `k8s/`, `helm/heart-disease/` (Deployment, Service, Ingress, HPA, NetworkPolicy) |
| 8. Monitoring & logging | 3 | `/metrics` (Prometheus), JSON logs, Grafana dashboard |
| 9. Documentation & report | 2 | `README.md`, `reports/Final_Report.docx`, `reports/architecture.png` |

---

## Generating the final report

```bash
.venv/bin/python reports/architecture_diagram.py     # writes reports/architecture.png
.venv/bin/python reports/generate_report.py          # writes reports/Final_Report.docx
```

The report embeds the EDA plots (`artifacts/plots/eda/`), training plots (`artifacts/plots/`), and the architecture diagram. Run the EDA notebook and `make train` first so all images exist.

---

## License

Educational use only — submitted as part of the BITS Pilani M.Tech MLOps assignment.
