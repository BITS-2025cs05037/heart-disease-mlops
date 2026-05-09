"""Evaluation utilities — metrics + plots.

Kept separate from `train.py` so the same helpers can be reused from
notebooks and tests without dragging in MLflow.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless rendering in CI / Docker
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from sklearn.metrics import (
    accuracy_score,
    auc,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)


def compute_metrics(y_true, y_pred, y_proba) -> dict[str, float]:
    """Return a flat dict of headline classification metrics."""
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, y_proba)),
    }


def save_confusion_matrix(y_true, y_pred, out_path: Path, title: str = "Confusion Matrix") -> Path:
    """Render a labelled confusion-matrix heatmap."""
    cm = confusion_matrix(y_true, y_pred)
    fig, ax = plt.subplots(figsize=(5, 4), dpi=120)
    sns.heatmap(
        cm,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=["No disease", "Disease"],
        yticklabels=["No disease", "Disease"],
        ax=ax,
    )
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title(title)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def save_roc_curve(y_true, y_proba, out_path: Path, title: str = "ROC Curve") -> Path:
    """Render a ROC curve with AUC annotation."""
    fpr, tpr, _ = roc_curve(y_true, y_proba)
    roc_auc = auc(fpr, tpr)
    fig, ax = plt.subplots(figsize=(5, 4), dpi=120)
    ax.plot(fpr, tpr, label=f"AUC = {roc_auc:0.3f}", linewidth=2)
    ax.plot([0, 1], [0, 1], linestyle="--", color="gray", linewidth=1)
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title(title)
    ax.legend(loc="lower right")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def feature_importance_plot(model, feature_names: list[str], out_path: Path) -> Path | None:
    """If the underlying classifier exposes feature_importances_, plot the top 20."""
    importances: np.ndarray | None
    importances = getattr(model, "feature_importances_", None)
    if importances is None:
        coef = getattr(model, "coef_", None)
        importances = np.abs(coef[0]) if coef is not None else None
    if importances is None:
        return None

    order = np.argsort(importances)[::-1][:20]
    fig, ax = plt.subplots(figsize=(7, 5), dpi=120)
    ax.barh(
        np.array(feature_names)[order][::-1],
        importances[order][::-1],
        color="#3a86ff",
    )
    ax.set_title("Top feature importances")
    ax.set_xlabel("Importance")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    return out_path
