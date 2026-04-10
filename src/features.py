"""Feature loading and preprocessing for dispute escalation models.

Expects data/processed/features.parquet (or .csv) produced by
scripts/build_dataset.py.

Usage::

    from src.features import load_features, prepare_X

    df = load_features()
    X, feature_names = prepare_X(df)
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from src.targets import PREDICTOR_COLS

logger = logging.getLogger(__name__)

DEFAULT_PARQUET = Path("data/processed/features.parquet")
DEFAULT_CSV = Path("data/processed/features.csv")


def load_features(path: Path | None = None) -> pd.DataFrame:
    """Load the feature matrix, preferring parquet then CSV.

    Raises FileNotFoundError with a helpful message if neither exists.
    """
    candidates = [path] if path else [DEFAULT_PARQUET, DEFAULT_CSV]

    for candidate in candidates:
        if candidate is None:
            continue
        if not candidate.exists():
            continue
        logger.info("Loading features from %s", candidate)
        if candidate.suffix == ".parquet":
            try:
                return pd.read_parquet(candidate)
            except ImportError:
                logger.warning(
                    "pyarrow not installed, falling back to CSV. "
                    "Install with: uv pip install pyarrow"
                )
                csv_candidate = candidate.with_suffix(".csv")
                if csv_candidate.exists():
                    return pd.read_csv(csv_candidate)
        else:
            return pd.read_csv(candidate)

    raise FileNotFoundError(
        "Feature matrix not found. Run 'make build-dataset' first.\n"
        f"  Expected: {DEFAULT_PARQUET} or {DEFAULT_CSV}"
    )


def prepare_X(
    df: pd.DataFrame,
    feature_cols: list[str] | None = None,
    fill_value: float = 0.0,
) -> tuple[pd.DataFrame, list[str]]:
    """Select predictor columns and fill missing values.

    Args:
        df: Raw feature matrix from load_features().
        feature_cols: Columns to use (defaults to PREDICTOR_COLS from targets.py).
        fill_value: Value used to impute NaN (default 0).

    Returns:
        (X, feature_names) — cleaned DataFrame and corresponding column names.
    """
    cols = feature_cols or PREDICTOR_COLS

    # Keep only columns that exist in this DataFrame
    available = [c for c in cols if c in df.columns]
    missing = set(cols) - set(available)
    if missing:
        logger.warning("Feature columns not found in DataFrame: %s", sorted(missing))

    X = df[available].copy().fillna(fill_value)
    return X, available


def log_feature_summary(df: pd.DataFrame, feature_cols: list[str]) -> None:
    """Log a quick summary of feature distributions."""
    X = df[feature_cols] if all(c in df.columns for c in feature_cols) else df
    logger.info("Feature matrix: %d rows × %d cols", len(X), len(X.columns))
    for col in X.columns:
        if X[col].dtype in (float, int) or pd.api.types.is_numeric_dtype(X[col]):
            logger.debug(
                "  %s: min=%.1f mean=%.1f max=%.1f",
                col,
                X[col].min(),
                X[col].mean(),
                X[col].max(),
            )
