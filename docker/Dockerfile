# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# Multi-stage Dockerfile for the Heart Disease prediction API.
#   stage 1 (builder): install dependencies into a wheelhouse + venv
#   stage 2 (runtime): copy the pre-built venv and only the runtime code
#                      into a slim, non-root container.
# Hardening:
#   * pinned base image with a digest-pinnable tag
#   * non-root UID 10001 (matches K8s securityContext)
#   * read-only filesystem-ready (no in-image writes at runtime)
#   * HEALTHCHECK calls /health
# ---------------------------------------------------------------------------

ARG PYTHON_VERSION=3.11.10

# ============================================================================
# Stage 1 — builder
# ============================================================================
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv

# Build deps for any wheels that need compilation (numpy/scipy ship wheels,
# but we keep a minimal toolchain for safety).
RUN apt-get update \
 && apt-get install --no-install-recommends -y build-essential \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /build
COPY requirements.txt ./requirements.txt
RUN pip install --upgrade pip \
 && pip install -r requirements.txt

# ============================================================================
# Stage 2 — runtime
# ============================================================================
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    MODEL_PATH=/app/artifacts/models/model.pkl \
    PORT=8000

# curl is needed only for HEALTHCHECK; remove apt cache to slim image.
RUN apt-get update \
 && apt-get install --no-install-recommends -y curl tini \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 appuser \
 && useradd  --system --uid 10001 --gid appuser --create-home appuser

WORKDIR /app

# Copy the pre-built virtualenv from the builder stage.
COPY --from=builder /opt/venv /opt/venv

# Copy ONLY runtime artifacts.  Source is intentionally minimal.
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser artifacts/models/ ./artifacts/models/

USER appuser

EXPOSE 8000

# tini reaps zombie children correctly when uvicorn forks workers.
ENTRYPOINT ["/usr/bin/tini", "--"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
