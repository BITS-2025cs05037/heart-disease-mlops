.PHONY: help install install-dev download-data train test lint format clean api \
        container-build container-run container-stop compose-up compose-down \
        docker-build docker-run mlflow-ui report

PYTHON ?= python3.11
VENV   ?= .venv
PIP    := $(VENV)/bin/pip
PY     := $(VENV)/bin/python

# ---------------------------------------------------------------------------
# Container runtime auto-detection.
# Honour an explicit override (CONTAINER_RUNTIME=podman make container-build),
# otherwise prefer docker, fall back to podman. Both speak the same CLI for
# the operations we use (build/run/rm/logs/exec).
# ---------------------------------------------------------------------------
CONTAINER_RUNTIME ?= $(shell command -v docker >/dev/null 2>&1 && echo docker || (command -v podman >/dev/null 2>&1 && echo podman || echo ""))
COMPOSE ?= $(shell command -v docker >/dev/null 2>&1 && echo "docker compose" || (command -v podman >/dev/null 2>&1 && echo "podman compose" || echo ""))
IMAGE   ?= heart-disease-api:latest

help:
	@echo "make venv             - create local virtualenv"
	@echo "make install          - install runtime deps"
	@echo "make install-dev      - install dev/test deps"
	@echo "make download-data    - download UCI Heart Disease dataset"
	@echo "make train            - train models + log to MLflow"
	@echo "make test             - run pytest"
	@echo "make lint             - run ruff"
	@echo "make format           - run black"
	@echo "make api              - run FastAPI locally"
	@echo "make container-build  - build image with $$(CONTAINER_RUNTIME) [docker or podman]"
	@echo "make container-run    - run image on :8000"
	@echo "make container-stop   - stop the running container"
	@echo "make compose-up       - bring up API + Prometheus + Grafana stack"
	@echo "make compose-down     - tear down compose stack"
	@echo "make docker-build     - alias for container-build (back-compat)"
	@echo "make docker-run       - alias for container-run   (back-compat)"
	@echo "make mlflow-ui        - launch MLflow UI on :5000"
	@echo "make report           - generate final report .docx"
	@echo ""
	@echo "Detected runtime: $(CONTAINER_RUNTIME)   |   compose: $(COMPOSE)"

venv:
	$(PYTHON) -m venv $(VENV)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

install-dev: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt

download-data:
	$(PY) scripts/download_data.py

train:
	$(PY) -m src.train

test:
	$(PY) -m pytest --cov=src --cov-report=term-missing

lint:
	$(VENV)/bin/ruff check src tests scripts
	$(VENV)/bin/black --check src tests scripts

format:
	$(VENV)/bin/ruff check --fix src tests scripts
	$(VENV)/bin/black src tests scripts

clean:
	rm -rf $(VENV) .pytest_cache .coverage htmlcov mlruns artifacts/models/*.pkl artifacts/plots/*.png

api:
	$(PY) -m uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload

container-build:
	@if [ -z "$(CONTAINER_RUNTIME)" ]; then \
		echo "ERROR: neither docker nor podman is on PATH"; exit 1; fi
	$(CONTAINER_RUNTIME) build -f docker/Dockerfile -t $(IMAGE) .

container-run:
	@if [ -z "$(CONTAINER_RUNTIME)" ]; then \
		echo "ERROR: neither docker nor podman is on PATH"; exit 1; fi
	$(CONTAINER_RUNTIME) run --rm -d -p 8000:8000 --name heart-api $(IMAGE)
	@echo "API: http://localhost:8000/docs   |   stop with: make container-stop"

container-stop:
	-$(CONTAINER_RUNTIME) rm -f heart-api 2>/dev/null

compose-up:
	@if [ -z "$(COMPOSE)" ]; then \
		echo "ERROR: neither 'docker compose' nor 'podman compose' is available"; exit 1; fi
	$(COMPOSE) up --build

compose-down:
	@if [ -z "$(COMPOSE)" ]; then exit 0; fi
	$(COMPOSE) down

# Back-compat aliases — many tutorials say "docker-build/docker-run".
docker-build: container-build
docker-run: container-run

mlflow-ui:
	$(VENV)/bin/mlflow ui --host 0.0.0.0 --port 5000

report:
	$(PY) reports/architecture_diagram.py
	$(PY) reports/generate_report.py
