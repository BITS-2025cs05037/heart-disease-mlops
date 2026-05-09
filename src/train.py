"""End-to-end training entrypoint with MLflow experiment tracking.

Trains three classifiers (Logistic Regression, Random Forest,
Gradient Boosting) with 5-fold stratified CV + grid search, logs every
run to MLflow with parameters / metrics / plots, registers the best
model under the canonical name "heart-disease-classifier", and persists
a pickled artifact at ``artifacts/models/model.pkl`` for the API to load
in containerised deployments.

Run:
    python -m src.train
or:
    make train
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import joblib
import mlflow
import mlflow.sklearn
import pandas as pd
from sklearn.base import BaseEstimator
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GridSearchCV, StratifiedKFold

from .data_loader import (
    ALL_FEATURES,
    DEFAULT_RANDOM_STATE,
    PROCESSED_CSV,
    get_train_test,
)
from .evaluate import (
    compute_metrics,
    feature_importance_plot,
    save_confusion_matrix,
    save_roc_curve,
)
from .preprocessing import build_full_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("train")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = PROJECT_ROOT / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "models" / "model.pkl"
METRICS_PATH = ARTIFACT_DIR / "models" / "metrics.json"
PLOT_DIR = ARTIFACT_DIR / "plots"

EXPERIMENT_NAME = "heart-disease"
REGISTERED_MODEL_NAME = "heart-disease-classifier"


@dataclass(frozen=True)
class ModelSpec:
    """Container pairing a classifier with the hyper-parameter grid we sweep."""

    name: str
    estimator: BaseEstimator
    param_grid: dict[str, list]


def get_model_specs(random_state: int = DEFAULT_RANDOM_STATE) -> list[ModelSpec]:
    """Return the catalogue of candidate models.

    ``classifier__*`` keys target the second step of the wrapping
    pipeline so GridSearchCV tunes the model only, not preprocessing.
    """
    return [
        ModelSpec(
            name="logistic_regression",
            estimator=LogisticRegression(
                max_iter=1000,
                solver="liblinear",
                random_state=random_state,
            ),
            param_grid={
                "classifier__C": [0.05, 0.1, 0.5, 1.0, 5.0],
                "classifier__penalty": ["l1", "l2"],
            },
        ),
        ModelSpec(
            name="random_forest",
            estimator=RandomForestClassifier(
                random_state=random_state,
                n_jobs=-1,
            ),
            param_grid={
                "classifier__n_estimators": [200, 400],
                "classifier__max_depth": [None, 5, 10],
                "classifier__min_samples_split": [2, 5],
            },
        ),
        ModelSpec(
            name="gradient_boosting",
            estimator=GradientBoostingClassifier(random_state=random_state),
            param_grid={
                "classifier__n_estimators": [100, 200],
                "classifier__learning_rate": [0.05, 0.1],
                "classifier__max_depth": [2, 3],
            },
        ),
    ]


def _expanded_feature_names(pipeline) -> list[str]:
    """Best-effort recovery of post-encoding feature names for plots."""
    try:
        return list(pipeline.named_steps["preprocessor"].get_feature_names_out())
    except Exception:  # noqa: BLE001
        return list(ALL_FEATURES)


def _train_one_model(
    spec: ModelSpec,
    X_train,
    X_test,
    y_train,
    y_test,
    cv_splits: int,
    random_state: int,
) -> tuple[GridSearchCV, dict[str, float]]:
    """Run a single grid search and produce evaluation metrics + artifacts."""
    log.info("=" * 70)
    log.info("Training: %s", spec.name)

    full_pipeline = build_full_pipeline(spec.estimator)

    cv = StratifiedKFold(n_splits=cv_splits, shuffle=True, random_state=random_state)
    grid = GridSearchCV(
        full_pipeline,
        spec.param_grid,
        cv=cv,
        scoring="roc_auc",
        n_jobs=-1,
        refit=True,
        return_train_score=False,
    )

    with mlflow.start_run(run_name=spec.name) as run:
        grid.fit(X_train, y_train)
        best_pipeline = grid.best_estimator_

        # Evaluate on held-out test set
        y_pred = best_pipeline.predict(X_test)
        y_proba = best_pipeline.predict_proba(X_test)[:, 1]
        metrics = compute_metrics(y_test, y_pred, y_proba)
        metrics["cv_roc_auc_mean"] = float(grid.best_score_)

        # Log hyperparameters that won the grid
        mlflow.log_param("model_family", spec.name)
        mlflow.log_param("cv_splits", cv_splits)
        mlflow.log_param("random_state", random_state)
        for key, value in grid.best_params_.items():
            mlflow.log_param(key, value)
        mlflow.log_metrics(metrics)

        # Persist plots and log them as MLflow artifacts
        cm_path = PLOT_DIR / f"{spec.name}_confusion_matrix.png"
        save_confusion_matrix(
            y_test, y_pred, cm_path, title=f"{spec.name} confusion matrix"
        )
        mlflow.log_artifact(str(cm_path), artifact_path="plots")

        roc_path = PLOT_DIR / f"{spec.name}_roc.png"
        save_roc_curve(y_test, y_proba, roc_path, title=f"{spec.name} ROC")
        mlflow.log_artifact(str(roc_path), artifact_path="plots")

        feat_path = PLOT_DIR / f"{spec.name}_feature_importance.png"
        if feature_importance_plot(
            best_pipeline.named_steps["classifier"],
            _expanded_feature_names(best_pipeline),
            feat_path,
        ):
            mlflow.log_artifact(str(feat_path), artifact_path="plots")

        # Log the full pipeline as an MLflow model — guarantees the served
        # artifact uses the SAME preprocessing as the training run.
        mlflow.sklearn.log_model(
            sk_model=best_pipeline,
            artifact_path="model",
            registered_model_name=None,  # registration happens once for the winner
        )

        log.info("Best params for %s: %s", spec.name, grid.best_params_)
        log.info("Test metrics for %s: %s", spec.name, metrics)
        log.info("MLflow run_id: %s", run.info.run_id)

    return grid, metrics


def train_all(
    csv_path: Path | None = None,
    cv_splits: int = 5,
    random_state: int = DEFAULT_RANDOM_STATE,
    test_size: float = 0.2,
    tracking_uri: str | None = None,
    experiment_name: str = EXPERIMENT_NAME,
) -> dict:
    """Train the catalogue of models and persist the best one."""
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)
    else:
        mlflow.set_tracking_uri(f"file:{(PROJECT_ROOT / 'mlruns').resolve()}")
    mlflow.set_experiment(experiment_name)

    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

    X_train, X_test, y_train, y_test = get_train_test(
        csv_path=csv_path or PROCESSED_CSV,
        test_size=test_size,
        random_state=random_state,
    )
    log.info("Train shape=%s | Test shape=%s", X_train.shape, X_test.shape)

    leaderboard: list[tuple[str, float, GridSearchCV, dict[str, float]]] = []
    for spec in get_model_specs(random_state):
        grid, metrics = _train_one_model(
            spec,
            X_train,
            X_test,
            y_train,
            y_test,
            cv_splits=cv_splits,
            random_state=random_state,
        )
        leaderboard.append((spec.name, metrics["roc_auc"], grid, metrics))

    # Winner = highest test ROC-AUC; ties broken by name for determinism.
    leaderboard.sort(key=lambda x: (-x[1], x[0]))
    best_name, _, best_grid, best_metrics = leaderboard[0]
    log.info("Winner: %s (test ROC-AUC=%.4f)", best_name, best_metrics["roc_auc"])

    # Persist the winning pipeline locally for the API container.
    joblib.dump(best_grid.best_estimator_, MODEL_PATH)
    log.info("Saved winning pipeline to %s", MODEL_PATH)

    summary = {
        "winner": best_name,
        "best_params": {k: str(v) for k, v in best_grid.best_params_.items()},
        "metrics": best_metrics,
        "leaderboard": [
            {"model": name, "roc_auc": auc_, "metrics": m}
            for name, auc_, _, m in leaderboard
        ],
    }
    METRICS_PATH.write_text(json.dumps(summary, indent=2))
    log.info("Wrote metrics summary to %s", METRICS_PATH)

    # Register the winner under a stable name so downstream stages can
    # reference it without hard-coding a run-id.
    with mlflow.start_run(run_name=f"register-{best_name}") as run:
        mlflow.log_params({f"best_{k}": v for k, v in best_grid.best_params_.items()})
        mlflow.log_metrics({f"best_{k}": v for k, v in best_metrics.items()})
        mlflow.sklearn.log_model(
            sk_model=best_grid.best_estimator_,
            artifact_path="model",
            registered_model_name=REGISTERED_MODEL_NAME,
        )
        log.info("Registered model under '%s' (run_id=%s)", REGISTERED_MODEL_NAME, run.info.run_id)

    return summary


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=None, help="Override processed CSV path")
    parser.add_argument("--cv-splits", type=int, default=5)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=DEFAULT_RANDOM_STATE)
    parser.add_argument(
        "--tracking-uri",
        type=str,
        default=None,
        help="Override MLflow tracking URI (default: file:./mlruns)",
    )
    parser.add_argument("--experiment-name", type=str, default=EXPERIMENT_NAME)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    summary = train_all(
        csv_path=args.csv,
        cv_splits=args.cv_splits,
        random_state=args.random_state,
        test_size=args.test_size,
        tracking_uri=args.tracking_uri,
        experiment_name=args.experiment_name,
    )
    print(pd.DataFrame(summary["leaderboard"]).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
