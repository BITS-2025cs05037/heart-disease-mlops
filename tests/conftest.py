"""Shared pytest fixtures.

We synthesise a small, deterministic dataset with the canonical schema so
the tests do NOT require the real CSV to be downloaded.  This keeps unit
tests hermetic and CI fast.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression


@pytest.fixture(scope="session")
def synthetic_dataframe() -> pd.DataFrame:
    """Return a 200-row, schema-correct, signal-bearing dataset."""
    rng = np.random.default_rng(42)
    n = 200

    df = pd.DataFrame(
        {
            "age": rng.integers(29, 78, size=n),
            "sex": rng.integers(0, 2, size=n),
            "cp": rng.integers(1, 5, size=n),
            "trestbps": rng.integers(94, 200, size=n).astype(float),
            "chol": rng.integers(126, 564, size=n).astype(float),
            "fbs": rng.integers(0, 2, size=n),
            "restecg": rng.integers(0, 3, size=n),
            "thalach": rng.integers(71, 202, size=n).astype(float),
            "exang": rng.integers(0, 2, size=n),
            "oldpeak": rng.uniform(0, 6.2, size=n).round(1),
            "slope": rng.integers(1, 4, size=n),
            "ca": rng.integers(0, 4, size=n).astype(float),
            "thal": rng.choice([3, 6, 7], size=n),
        }
    )
    # Engineer a non-trivial target so models can learn (>0.6 AUC).
    risk = (
        0.04 * (df["age"] - 50)
        + 0.6 * (df["cp"] >= 3).astype(int)
        + 0.5 * (df["exang"] == 1).astype(int)
        + 0.4 * (df["oldpeak"] > 1.5).astype(int)
        + rng.normal(0, 0.5, size=n)
    )
    df["target"] = (risk > 0.5).astype(int)
    return df


@pytest.fixture(scope="session")
def synthetic_csv(tmp_path_factory, synthetic_dataframe) -> Path:
    """Persist the synthetic dataframe to a CSV the modules can load."""
    out = tmp_path_factory.mktemp("data") / "heart_disease.csv"
    synthetic_dataframe.to_csv(out, index=False)
    return out


@pytest.fixture(scope="session")
def trained_pipeline(synthetic_dataframe):
    """Train a tiny pipeline once per test session; reused by API + I/O tests."""
    from src.data_loader import ALL_FEATURES, TARGET_COLUMN
    from src.preprocessing import build_full_pipeline

    pipe = build_full_pipeline(LogisticRegression(max_iter=500, random_state=0))
    pipe.fit(synthetic_dataframe[ALL_FEATURES], synthetic_dataframe[TARGET_COLUMN])
    return pipe
