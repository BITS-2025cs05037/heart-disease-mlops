"""Render the system architecture diagram as a PNG.

Output: reports/architecture.png

The diagram is composed with matplotlib (no graphviz dependency) so it
works in CI and locally without extra installs.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent / "architecture.png"


def _box(ax, x, y, w, h, text, color):
    box = mpatches.FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.06,rounding_size=0.18",
        linewidth=1.5,
        edgecolor="#222",
        facecolor=color,
        alpha=0.95,
    )
    ax.add_patch(box)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=10, weight="bold")


def _arrow(ax, x1, y1, x2, y2, label: str | None = None):
    ax.annotate(
        "",
        xy=(x2, y2),
        xytext=(x1, y1),
        arrowprops=dict(arrowstyle="->", color="#222", lw=1.6, shrinkA=4, shrinkB=4),
    )
    if label:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.18, label, ha="center", fontsize=8, color="#444")


def render() -> Path:
    fig, ax = plt.subplots(figsize=(13, 9), dpi=140)
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 9)
    ax.axis("off")
    ax.set_title(
        "Heart Disease MLOps — End-to-End Architecture",
        fontsize=14,
        weight="bold",
        pad=16,
    )

    dev = "#cdb4db"
    train = "#a2d2ff"
    cicd = "#ffafcc"
    cluster = "#bde0fe"
    monitor = "#caffbf"

    # Row 1 — developer + source
    _box(ax, 0.3, 7.4, 2.4, 1.0, "Developer", dev)
    _box(ax, 3.4, 7.4, 2.4, 1.0, "GitHub Repo", dev)
    _box(ax, 6.5, 7.4, 2.4, 1.0, "GitHub Actions\n(CI/CD)", cicd)

    _arrow(ax, 2.7, 7.9, 3.4, 7.9, "git push")
    _arrow(ax, 5.8, 7.9, 6.5, 7.9, "trigger")

    # Row 2 — training pipeline
    _box(ax, 0.3, 5.5, 2.4, 1.0, "UCI dataset\n(download script)", train)
    _box(ax, 3.4, 5.5, 2.4, 1.0, "Preprocessing\nPipeline", train)
    _box(ax, 6.5, 5.5, 2.4, 1.0, "Train + Tune\n(LR / RF / GBM)", train)
    _box(ax, 9.6, 5.5, 2.8, 1.0, "MLflow Tracking\n(params/metrics/plots)", train)

    _arrow(ax, 2.7, 6.0, 3.4, 6.0)
    _arrow(ax, 5.8, 6.0, 6.5, 6.0)
    _arrow(ax, 8.9, 6.0, 9.6, 6.0)
    _arrow(ax, 7.7, 7.4, 7.7, 6.5, "build & test")

    # Row 3 — packaging & registry
    _box(ax, 3.4, 3.7, 2.4, 1.0, "model.pkl\n(joblib)", train)
    _box(ax, 6.5, 3.7, 2.4, 1.0, "Docker image\n(multi-stage)", cicd)
    _box(ax, 9.6, 3.7, 2.8, 1.0, "MLflow Model\nRegistry", train)

    _arrow(ax, 4.6, 5.5, 4.6, 4.7)
    _arrow(ax, 5.8, 4.2, 6.5, 4.2, "COPY into image")
    _arrow(ax, 11.0, 5.5, 11.0, 4.7)

    # Row 4 — Kubernetes
    _box(ax, 0.3, 1.6, 12.4, 1.4, "Kubernetes Cluster (Minikube / GKE / EKS / AKS)", cluster)
    _box(ax, 0.6, 1.85, 2.6, 0.9, "Ingress / LB", cluster)
    _box(ax, 3.5, 1.85, 2.6, 0.9, "Service\n(ClusterIP)", cluster)
    _box(ax, 6.4, 1.85, 2.6, 0.9, "Deployment\n+ HPA (2-6 pods)", cluster)
    _box(ax, 9.3, 1.85, 3.1, 0.9, "Pods: FastAPI + uvicorn\n(non-root, RO FS)", cluster)

    _arrow(ax, 7.7, 3.7, 7.7, 2.8, "kubectl apply")

    # Row 5 — monitoring + clients
    _box(ax, 0.3, 0.2, 2.6, 0.9, "End User\n(curl / Swagger)", monitor)
    _box(ax, 3.4, 0.2, 2.6, 0.9, "Prometheus\n(/metrics scrape)", monitor)
    _box(ax, 6.5, 0.2, 2.6, 0.9, "Grafana\nDashboards", monitor)
    _box(ax, 9.6, 0.2, 2.8, 0.9, "Logs (stdout JSON)\n+ alerts", monitor)

    _arrow(ax, 1.6, 1.1, 1.6, 1.6, "HTTPS")
    _arrow(ax, 4.7, 1.6, 4.7, 1.1, "scrape")
    _arrow(ax, 4.7, 0.65, 6.5, 0.65, "PromQL")
    _arrow(ax, 9.0, 1.6, 10.5, 1.1, "stdout")

    # Legend
    legend = [
        mpatches.Patch(color=dev, label="Source / Developer"),
        mpatches.Patch(color=train, label="Training & Experimentation"),
        mpatches.Patch(color=cicd, label="CI/CD"),
        mpatches.Patch(color=cluster, label="Production Runtime (K8s)"),
        mpatches.Patch(color=monitor, label="Observability"),
    ]
    ax.legend(handles=legend, loc="upper left", bbox_to_anchor=(0.0, 1.05), ncol=5, fontsize=8)

    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, bbox_inches="tight")
    plt.close(fig)
    return OUT


if __name__ == "__main__":
    print(f"Wrote {render()}")
