"""Dataset access helpers for the Heart Disease project.

This module is the single source of truth for:
    * the location of the processed CSV
    * the canonical feature/target column names
    * the train/test split protocol

Keeping these constants here avoids duplication and lets the unit tests in
tests/ verify the contract without re-implementing it.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_CSV = PROJECT_ROOT / "data" / "processed" / "heart_disease.csv"

TARGET_COLUMN = "target"

# Categorical features (one-hot encoded by the preprocessor)
CATEGORICAL_FEATURES: list[str] = [
    "sex",
    "cp",
    "fbs",
    "restecg",
    "exang",
    "slope",
    "thal",
]

# Numeric features (median-imputed + scaled)
NUMERIC_FEATURES: list[str] = [
    "age",
    "trestbps",
    "chol",
    "thalach",
    "oldpeak",
    "ca",
]

ALL_FEATURES: list[str] = NUMERIC_FEATURES + CATEGORICAL_FEATURES

DEFAULT_TEST_SIZE = 0.2
DEFAULT_RANDOM_STATE = 42


def load_processed(csv_path: Path | str | None = None) -> pd.DataFrame:
    """Load the cleaned, model-ready CSV.

    Raises a clear error if the file is missing so the user knows to run the
    download script first.
    """
    path = Path(csv_path) if csv_path else PROCESSED_CSV
    if not path.exists():
        raise FileNotFoundError(
            f"Processed dataset not found at {path}. "
            "Run `python scripts/download_data.py` first."
        )
    df = pd.read_csv(path)
    log.info("Loaded processed dataset: shape=%s", df.shape)
    return df


def split_features_target(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Split a dataframe into the X / y pair using the canonical schema."""
    missing = [c for c in ALL_FEATURES + [TARGET_COLUMN] if c not in df.columns]
    if missing:
        raise ValueError(f"Dataset is missing required columns: {missing}")
    X = df[ALL_FEATURES].copy()
    y = df[TARGET_COLUMN].astype(int).copy()
    return X, y


def get_train_test(
    csv_path: Path | str | None = None,
    test_size: float = DEFAULT_TEST_SIZE,
    random_state: int = DEFAULT_RANDOM_STATE,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Return X_train, X_test, y_train, y_test using a stratified split.

    Stratification is important because the dataset is mildly imbalanced
    (~54% positive) and we want both splits to reflect prevalence.
    """
    df = load_processed(csv_path)
    X, y = split_features_target(df)
    return train_test_split(
        X,
        y,
        test_size=test_size,
        random_state=random_state,
        stratify=y,
    )
