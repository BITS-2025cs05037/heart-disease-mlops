"""Tests for `src.data_loader`."""

from __future__ import annotations

import pytest

from src.data_loader import (
    ALL_FEATURES,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    TARGET_COLUMN,
    get_train_test,
    load_processed,
    split_features_target,
)


def test_feature_lists_are_disjoint_and_cover_all_features():
    assert set(NUMERIC_FEATURES).isdisjoint(set(CATEGORICAL_FEATURES))
    assert set(ALL_FEATURES) == set(NUMERIC_FEATURES) | set(CATEGORICAL_FEATURES)


def test_load_processed_raises_friendly_error_for_missing_file(tmp_path):
    missing = tmp_path / "no_such_file.csv"
    with pytest.raises(FileNotFoundError, match="Processed dataset not found"):
        load_processed(missing)


def test_load_processed_loads_synthetic_csv(synthetic_csv):
    df = load_processed(synthetic_csv)
    assert TARGET_COLUMN in df.columns
    assert len(df) > 0
    for col in ALL_FEATURES:
        assert col in df.columns, f"missing column: {col}"


def test_split_features_target_returns_correct_shapes(synthetic_dataframe):
    X, y = split_features_target(synthetic_dataframe)
    assert list(X.columns) == ALL_FEATURES
    assert len(X) == len(y) == len(synthetic_dataframe)
    assert TARGET_COLUMN not in X.columns
    assert set(y.unique()).issubset({0, 1})


def test_split_features_target_reports_missing_columns(synthetic_dataframe):
    df = synthetic_dataframe.drop(columns=["age"])
    with pytest.raises(ValueError, match="missing required columns"):
        split_features_target(df)


def test_get_train_test_is_stratified_and_reproducible(synthetic_csv):
    X1, X2, y1, y2 = get_train_test(synthetic_csv, test_size=0.25, random_state=7)
    X1b, X2b, y1b, y2b = get_train_test(synthetic_csv, test_size=0.25, random_state=7)

    assert X1.equals(X1b) and X2.equals(X2b)
    assert y1.equals(y1b) and y2.equals(y2b)

    # Stratification: positive rate within 5pp of overall rate
    overall_rate = (y1.sum() + y2.sum()) / (len(y1) + len(y2))
    assert abs((y1.mean()) - overall_rate) < 0.05
    assert abs((y2.mean()) - overall_rate) < 0.05
