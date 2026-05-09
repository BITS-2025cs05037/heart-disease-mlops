"""Tests for `src.preprocessing`."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from src.data_loader import ALL_FEATURES, CATEGORICAL_FEATURES, NUMERIC_FEATURES
from src.preprocessing import build_full_pipeline, build_preprocessor


def test_preprocessor_has_numeric_and_categorical_branches():
    preprocessor = build_preprocessor()
    transformer_names = {name for name, _, _ in preprocessor.transformers}
    assert {"num", "cat"}.issubset(transformer_names)


def test_preprocessor_handles_missing_values(synthetic_dataframe):
    df = synthetic_dataframe.copy()
    df.loc[df.index[:5], "ca"] = np.nan  # numeric column
    df.loc[df.index[:3], "thal"] = np.nan  # categorical column

    preprocessor = build_preprocessor()
    transformed = preprocessor.fit_transform(df[ALL_FEATURES])

    assert not np.isnan(transformed).any(), "preprocessor must not leak NaNs"


def test_preprocessor_scales_numeric_features(synthetic_dataframe):
    preprocessor = build_preprocessor()
    transformed = preprocessor.fit_transform(synthetic_dataframe[ALL_FEATURES])

    # Numeric block is the first len(NUMERIC_FEATURES) columns.
    numeric_block = transformed[:, : len(NUMERIC_FEATURES)]
    means = numeric_block.mean(axis=0)
    stds = numeric_block.std(axis=0)
    assert np.allclose(means, 0, atol=1e-7), "numeric features should be zero-centered"
    assert np.allclose(stds, 1, atol=1e-1), "numeric features should be ~unit-variance"


def test_preprocessor_one_hot_encodes_categoricals(synthetic_dataframe):
    preprocessor = build_preprocessor()
    transformed = preprocessor.fit_transform(synthetic_dataframe[ALL_FEATURES])

    # Cardinality of categorical block = total unique levels across cols.
    expected_cat_width = sum(synthetic_dataframe[c].nunique() for c in CATEGORICAL_FEATURES)
    cat_width = transformed.shape[1] - len(NUMERIC_FEATURES)
    assert cat_width == expected_cat_width


def test_preprocessor_handles_unseen_categories_at_inference(synthetic_dataframe):
    preprocessor = build_preprocessor().fit(synthetic_dataframe[ALL_FEATURES])

    novel = synthetic_dataframe.iloc[:1].copy()
    novel.loc[:, "cp"] = 99  # value never seen during fit
    # Should NOT raise — handle_unknown="ignore"
    out = preprocessor.transform(novel[ALL_FEATURES])
    assert out.shape[0] == 1


def test_build_full_pipeline_is_a_pipeline(synthetic_dataframe):
    pipe = build_full_pipeline(LogisticRegression(max_iter=500))
    assert isinstance(pipe, Pipeline)
    pipe.fit(synthetic_dataframe[ALL_FEATURES], synthetic_dataframe["target"])
    proba = pipe.predict_proba(synthetic_dataframe[ALL_FEATURES])
    assert proba.shape == (len(synthetic_dataframe), 2)
    assert np.allclose(proba.sum(axis=1), 1.0)


def test_pipeline_accepts_dictionary_payload(synthetic_dataframe):
    """Smoke test that mirrors how the API will call the pipeline."""
    pipe = build_full_pipeline(LogisticRegression(max_iter=500))
    pipe.fit(synthetic_dataframe[ALL_FEATURES], synthetic_dataframe["target"])
    payload = synthetic_dataframe[ALL_FEATURES].iloc[0].to_dict()
    df = pd.DataFrame([payload])
    pred = pipe.predict(df)
    assert pred.shape == (1,)
