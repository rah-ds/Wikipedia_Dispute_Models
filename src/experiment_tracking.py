"""MLflow experiment tracking utilities for Wikipedia Dispute Models.

Thin wrapper around MLflow that degrades gracefully when mlflow is not
installed, so importing this module never breaks non-model scripts.

Usage (in a training script)::

    from src.experiment_tracking import setup_mlflow, run, log_dataset, log_metrics

    setup_mlflow(experiment_name="wikipedia-dispute-escalation")

    with run(run_name="logistic-baseline", params={"C": 1.0, "max_iter": 1000}):
        # ... train model ...
        log_metrics({"accuracy": 0.82, "f1": 0.79, "roc_auc": 0.88})
        log_dataset(Path("data/processed/features.parquet"), context="training")

The MLflow UI can be launched with::

    make mlflow-ui
    # or: mlflow ui --backend-store-uri artifacts/mlruns

Environment variables:
  MLFLOW_TRACKING_URI   — override the default local tracking dir
  MLFLOW_EXPERIMENT     — override the default experiment name
"""

from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path
from typing import Any, Generator

logger = logging.getLogger(__name__)

DEFAULT_TRACKING_URI = "artifacts/mlruns"
DEFAULT_EXPERIMENT = "wikipedia-dispute-escalation"


def _mlflow():
    """Import mlflow, raising a clear error if it is missing."""
    try:
        import mlflow  # type: ignore[import]

        return mlflow
    except ImportError as exc:
        raise ImportError(
            "mlflow is not installed. Run: uv pip install 'wikipedia-arbitration[ml]'"
        ) from exc


def setup_mlflow(
    experiment_name: str | None = None,
    tracking_uri: str | None = None,
) -> None:
    """Configure MLflow tracking URI and experiment.

    Safe to call multiple times; subsequent calls are no-ops if the
    experiment is already active.
    """
    uri = tracking_uri or os.environ.get("MLFLOW_TRACKING_URI", DEFAULT_TRACKING_URI)
    name = experiment_name or os.environ.get("MLFLOW_EXPERIMENT", DEFAULT_EXPERIMENT)

    try:
        mlflow = _mlflow()
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment(name)
        logger.info("MLflow: tracking_uri=%s  experiment=%s", uri, name)
    except ImportError:
        logger.warning(
            "mlflow not installed — experiment tracking disabled. "
            "Install with: uv pip install 'wikipedia-arbitration[ml]'"
        )


@contextlib.contextmanager
def run(
    run_name: str | None = None,
    params: dict[str, Any] | None = None,
    tags: dict[str, str] | None = None,
) -> Generator[Any, None, None]:
    """Context manager for an MLflow run with graceful no-op fallback.

    Example::

        with run(run_name="my-experiment", params={"alpha": 0.5}) as active_run:
            if active_run:
                print(active_run.info.run_id)
            # train, evaluate, log metrics ...
    """
    try:
        mlflow = _mlflow()
        with mlflow.start_run(run_name=run_name, tags=tags) as active_run:
            if params:
                mlflow.log_params(params)
            yield active_run
    except ImportError:
        logger.warning("mlflow not installed — run() is a no-op.")
        yield None


def log_dataset(path: Path, context: str = "training") -> None:
    """Log a dataset file as an MLflow artifact in the active run."""
    try:
        mlflow = _mlflow()
        if not path.exists():
            logger.warning("Dataset not found, skipping artifact log: %s", path)
            return
        mlflow.log_artifact(str(path), artifact_path="datasets")
        mlflow.set_tag(f"dataset_{context}_path", str(path))
        mlflow.set_tag(f"dataset_{context}_name", path.name)
        logger.debug("Logged dataset artifact: %s", path)
    except ImportError:
        pass


def log_metrics(metrics: dict[str, float], step: int | None = None) -> None:
    """Log a dict of scalar metrics to the active MLflow run."""
    try:
        mlflow = _mlflow()
        mlflow.log_metrics(metrics, step=step)
        logger.debug("Logged metrics: %s", metrics)
    except ImportError:
        pass


def log_feature_importance(
    feature_names: list[str],
    importances: list[float],
) -> None:
    """Log feature importances as a CSV artifact."""
    import io

    try:
        mlflow = _mlflow()
        import csv

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["feature", "importance"])
        writer.writerows(
            sorted(zip(feature_names, importances), key=lambda x: x[1], reverse=True)
        )
        with (
            mlflow.start_run(nested=True)
            if not mlflow.active_run()
            else contextlib.nullcontext()
        ):
            mlflow.log_text(buf.getvalue(), "feature_importance.csv")
    except ImportError:
        pass
