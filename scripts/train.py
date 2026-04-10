#!/usr/bin/env python3
"""Baseline classification models for Wikipedia dispute outcomes.

Trains two baselines (logistic regression, random forest) for each
available target variable and logs results to MLflow.

Because the dataset is small (87 cases), this uses stratified K-fold
cross-validation rather than a hold-out split.

Usage:
    python scripts/train.py                           # all targets, all models
    python scripts/train.py --target was_sanctioned   # single target
    python scripts/train.py --model logistic          # single model
    python scripts/train.py --no-mlflow               # skip MLflow logging
    python scripts/train.py --features data/processed/features.csv

Targets:
    was_sanctioned  (binary, 24% positive) — did the case result in remedies?
    was_closed      (binary, 84% positive) — was the case formally closed?
    outcome_class   (3-class)              — sanctioned / dismissed / unresolved

Requires:
    make build-dataset        (produces data/processed/features.parquet)
    make install-ml           (installs scikit-learn, mlflow)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from features import load_features, prepare_X
from targets import (
    PREDICTOR_COLS,
    make_outcome_class,
    make_was_closed,
    make_was_sanctioned,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

_TARGET_BUILDERS = {
    "was_sanctioned": make_was_sanctioned,
    "was_closed": make_was_closed,
    "outcome_class": make_outcome_class,
}


def build_models(task: str) -> dict:
    """Return {name: estimator} for classification or multiclass."""
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        print("scikit-learn not installed. Run: make install-ml")
        sys.exit(1)

    if task == "binary":
        return {
            "logistic": Pipeline(
                [
                    ("scaler", StandardScaler()),
                    (
                        "clf",
                        LogisticRegression(
                            max_iter=1000, class_weight="balanced", random_state=42
                        ),
                    ),
                ]
            ),
            "random_forest": RandomForestClassifier(
                n_estimators=200,
                class_weight="balanced",
                random_state=42,
                n_jobs=-1,
            ),
        }
    else:  # multiclass
        return {
            "logistic": Pipeline(
                [
                    ("scaler", StandardScaler()),
                    (
                        "clf",
                        LogisticRegression(
                            max_iter=1000,
                            class_weight="balanced",
                            multi_class="multinomial",
                            random_state=42,
                        ),
                    ),
                ]
            ),
            "random_forest": RandomForestClassifier(
                n_estimators=200,
                class_weight="balanced",
                random_state=42,
                n_jobs=-1,
            ),
        }


# ---------------------------------------------------------------------------
# Cross-validation evaluation
# ---------------------------------------------------------------------------


def evaluate_cv(
    model,
    X: pd.DataFrame,
    y: pd.Series,
    n_splits: int = 5,
    task: str = "binary",
) -> dict[str, float]:
    """Stratified K-fold evaluation. Returns mean ± std of key metrics."""
    try:
        from sklearn.model_selection import StratifiedKFold, cross_validate
    except ImportError:
        print("scikit-learn not installed. Run: make install-ml")
        sys.exit(1)

    scoring = (
        ["roc_auc", "f1_weighted", "precision_weighted", "recall_weighted"]
        if task == "binary"
        else ["f1_weighted", "precision_weighted", "recall_weighted"]
    )

    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    scores = cross_validate(model, X, y, cv=cv, scoring=scoring, error_score="raise")

    results: dict[str, float] = {}
    for metric in scoring:
        key = f"test_{metric}"
        if key in scores:
            results[f"{metric}_mean"] = float(scores[key].mean())
            results[f"{metric}_std"] = float(scores[key].std())

    return results


# ---------------------------------------------------------------------------
# Main training loop
# ---------------------------------------------------------------------------


def train_target(
    target_name: str,
    df: pd.DataFrame,
    X: pd.DataFrame,
    use_mlflow: bool,
    model_filter: str | None,
) -> None:
    """Train all models for a single target variable."""
    y = _TARGET_BUILDERS[target_name](df)
    task = "multiclass" if target_name == "outcome_class" else "binary"
    models = build_models(task)

    if model_filter:
        models = {k: v for k, v in models.items() if k == model_filter}
        if not models:
            logger.error(
                "Unknown model: %s. Choose from: %s",
                model_filter,
                list(build_models(task)),
            )
            return

    pos_rate = (y != y.mode()[0]).mean() if task == "multiclass" else y.mean()
    print(f"\n{'=' * 60}")
    print(f"Target: {target_name}  (task={task}, n={len(y)}, pos_rate={pos_rate:.1%})")
    print(f"{'=' * 60}")

    for model_name, model in models.items():
        print(f"\n  Model: {model_name}")
        try:
            metrics = evaluate_cv(model, X, y, task=task)
        except Exception as e:
            logger.error("  CV failed for %s / %s: %s", target_name, model_name, e)
            continue

        for k, v in metrics.items():
            print(f"    {k}: {v:.4f}")

        if use_mlflow:
            _log_mlflow_run(target_name, model_name, metrics, X.columns.tolist(), model)


def _log_mlflow_run(
    target_name: str,
    model_name: str,
    metrics: dict[str, float],
    feature_names: list[str],
    model,
) -> None:
    """Log a single model's CV results to MLflow."""
    try:
        import mlflow

        mlflow.set_experiment("wikipedia-dispute-escalation")
        with mlflow.start_run(run_name=f"{target_name}/{model_name}"):
            mlflow.set_tag("target", target_name)
            mlflow.set_tag("model", model_name)
            mlflow.set_tag("n_features", len(feature_names))
            mlflow.log_params(
                {
                    "target": target_name,
                    "model": model_name,
                    "n_features": len(feature_names),
                    "cv_folds": 5,
                    "dataset": "data/processed/features.parquet",
                }
            )
            mlflow.log_metrics(metrics)
            mlflow.log_text("\n".join(feature_names), "feature_list.txt")
    except ImportError:
        logger.debug("mlflow not installed — skipping tracking.")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--target",
        choices=list(_TARGET_BUILDERS),
        default=None,
        help="Target variable to train. Default: all.",
    )
    parser.add_argument(
        "--model",
        choices=["logistic", "random_forest"],
        default=None,
        help="Model to train. Default: all.",
    )
    parser.add_argument(
        "--features",
        default=None,
        type=Path,
        help="Path to feature matrix (CSV or parquet). Default: auto-detect.",
    )
    parser.add_argument(
        "--no-mlflow",
        action="store_true",
        help="Skip MLflow logging.",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-8s %(message)s",
    )

    # Load data
    try:
        df = load_features(args.features)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    X, feature_names = prepare_X(df, PREDICTOR_COLS)
    print(f"Loaded {len(df)} cases × {len(feature_names)} features")

    # MLflow tracking URI
    if not args.no_mlflow:
        try:
            import mlflow

            mlflow.set_tracking_uri("artifacts/mlruns")
            print("MLflow tracking: artifacts/mlruns  (run 'make mlflow-ui' to view)")
        except ImportError:
            print("mlflow not installed — run 'make install-ml' to enable tracking")
            args.no_mlflow = True

    # Train
    targets_to_run = [args.target] if args.target else list(_TARGET_BUILDERS)
    for target_name in targets_to_run:
        train_target(
            target_name=target_name,
            df=df,
            X=X,
            use_mlflow=not args.no_mlflow,
            model_filter=args.model,
        )

    print("\nDone.")
    if not args.no_mlflow:
        print("View results: make mlflow-ui → http://localhost:5000")


if __name__ == "__main__":
    main()
