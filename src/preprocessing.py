"""Feature preprocessing pipeline.

Builds an :class:`sklearn.compose.ColumnTransformer` that:
  * imputes missing numeric values with the median, then scales them
    with StandardScaler;
  * imputes missing categorical values with the most frequent category,
    then one-hot encodes them (unknown categories at inference time are
    handled silently to avoid 500s in production).

The transformer is wrapped together with a classifier in
:func:`build_full_pipeline`, so the saved artifact is a single object that
encapsulates both feature engineering and the model — guaranteeing
reproducibility in the API container.
"""

from __future__ import annotations

from sklearn.base import BaseEstimator
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .data_loader import CATEGORICAL_FEATURES, NUMERIC_FEATURES


def build_preprocessor() -> ColumnTransformer:
    """Return a fitted-once, fit-twice-safe column transformer."""
    numeric_pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )

    categorical_pipe = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            (
                "onehot",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
            ),
        ]
    )

    return ColumnTransformer(
        transformers=[
            ("num", numeric_pipe, NUMERIC_FEATURES),
            ("cat", categorical_pipe, CATEGORICAL_FEATURES),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )


def build_full_pipeline(estimator: BaseEstimator) -> Pipeline:
    """Compose preprocessing + classifier into one persistable Pipeline.

    Wrapping classifier and preprocessor together is the recommended
    sklearn pattern; callers receive a single artifact whose ``.predict``
    handles raw, dictionary-style input from the API.
    """
    return Pipeline(
        steps=[
            ("preprocessor", build_preprocessor()),
            ("classifier", estimator),
        ]
    )
