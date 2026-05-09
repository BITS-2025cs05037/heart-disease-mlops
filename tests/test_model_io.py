"""Tests covering training-side artifact persistence and reloading."""

from __future__ import annotations

import joblib
import numpy as np
import pandas as pd

from src.data_loader import ALL_FEATURES


def test_pipeline_round_trip_via_joblib(tmp_path, trained_pipeline, synthetic_dataframe):
    """Persist + reload the pipeline; predictions must be byte-equal."""
    out = tmp_path / "model.pkl"
    joblib.dump(trained_pipeline, out)
    assert out.exists()

    reloaded = joblib.load(out)
    sample = synthetic_dataframe[ALL_FEATURES].iloc[:5]

    original = trained_pipeline.predict_proba(sample)
    new = reloaded.predict_proba(sample)
    np.testing.assert_allclose(original, new)


def test_pipeline_handles_dictionary_input(trained_pipeline):
    """The API submits one row at a time as a DataFrame from a dict."""
    payload = {
        "age": 63,
        "sex": 1,
        "cp": 3,
        "trestbps": 145,
        "chol": 233,
        "fbs": 1,
        "restecg": 0,
        "thalach": 150,
        "exang": 0,
        "oldpeak": 2.3,
        "slope": 1,
        "ca": 0,
        "thal": 6,
    }
    df = pd.DataFrame([payload])
    proba = trained_pipeline.predict_proba(df)
    assert proba.shape == (1, 2)
    assert 0.0 <= float(proba[0, 1]) <= 1.0
