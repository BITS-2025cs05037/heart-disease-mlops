"""Download and clean the UCI Heart Disease (Cleveland) dataset.

Source: UCI Machine Learning Repository
  https://archive.ics.uci.edu/ml/machine-learning-databases/heart-disease/

Usage:
    python scripts/download_data.py [--force]

Outputs:
    data/raw/heart_disease_raw.csv      (raw download with header added)
    data/processed/heart_disease.csv    (cleaned, missing values imputed,
                                         binary `target` column)

The script is deterministic and idempotent. Re-running with --force overwrites.
"""

from __future__ import annotations

import argparse
import logging
import sys
import urllib.request
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("download_data")

# Multiple mirrors for resilience; we try in order until one succeeds.
DATA_URLS: list[str] = [
    "https://archive.ics.uci.edu/ml/machine-learning-databases/heart-disease/processed.cleveland.data",
    "https://raw.githubusercontent.com/jbrownlee/Datasets/master/heart-disease.csv",
]

COLUMNS: list[str] = [
    "age",
    "sex",
    "cp",
    "trestbps",
    "chol",
    "fbs",
    "restecg",
    "thalach",
    "exang",
    "oldpeak",
    "slope",
    "ca",
    "thal",
    "num",
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_PATH = PROJECT_ROOT / "data" / "raw" / "heart_disease_raw.csv"
PROCESSED_PATH = PROJECT_ROOT / "data" / "processed" / "heart_disease.csv"


def download(force: bool = False) -> Path:
    """Download the raw CSV (with '?' as missing-value sentinels) to data/raw/."""
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    if RAW_PATH.exists() and not force:
        log.info("Raw file already present at %s (use --force to redownload)", RAW_PATH)
        return RAW_PATH

    last_error: Exception | None = None
    for url in DATA_URLS:
        try:
            log.info("Attempting download from %s", url)
            # urllib only supports http(s); URLs above are HTTPS.
            with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
                raw_bytes = resp.read()
            text = raw_bytes.decode("utf-8")
            # If file lacks header, prepend ours.
            first_line = text.splitlines()[0]
            if "age" not in first_line.lower():
                text = ",".join(COLUMNS) + "\n" + text
            RAW_PATH.write_text(text, encoding="utf-8")
            log.info("Saved raw dataset (%d bytes) to %s", len(raw_bytes), RAW_PATH)
            return RAW_PATH
        except Exception as exc:  # noqa: BLE001
            log.warning("Download from %s failed: %s", url, exc)
            last_error = exc

    raise RuntimeError(
        f"All download attempts failed. Last error: {last_error}. "
        "Please check your network or download manually."
    )


def clean_and_save() -> Path:
    """Clean the raw CSV and persist a model-ready processed CSV."""
    log.info("Loading raw CSV from %s", RAW_PATH)
    df = pd.read_csv(RAW_PATH, na_values=["?"])

    # Some upstream copies use `target` directly; normalise to `num` -> binary `target`.
    if "target" in df.columns and "num" not in df.columns:
        df["num"] = df["target"]
        df = df.drop(columns=["target"])

    if list(df.columns)[: len(COLUMNS)] != COLUMNS:
        # Header mismatch: enforce known schema where possible.
        log.warning("Column order does not match expected schema; coercing.")
        df = df.rename(columns={c: COLUMNS[i] for i, c in enumerate(df.columns[: len(COLUMNS)])})

    log.info("Raw shape: %s", df.shape)
    log.info("Missing values per column:\n%s", df.isna().sum().to_string())

    # Cast numeric columns properly (some may have been read as object due to '?').
    numeric_cols = [
        "age",
        "trestbps",
        "chol",
        "thalach",
        "oldpeak",
        "ca",
        "thal",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop rows where target is missing (cannot impute the label).
    df = df.dropna(subset=["num"]).copy()

    # Binarise the target: 0 = no disease, >=1 = disease.
    df["target"] = (df["num"] > 0).astype(int)
    df = df.drop(columns=["num"])

    PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED_PATH, index=False)
    log.info("Saved cleaned dataset (%d rows, %d cols) to %s", *df.shape, PROCESSED_PATH)
    log.info("Class balance:\n%s", df["target"].value_counts(normalize=True).to_string())
    return PROCESSED_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Re-download even if present")
    args = parser.parse_args()

    download(force=args.force)
    clean_and_save()
    log.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
