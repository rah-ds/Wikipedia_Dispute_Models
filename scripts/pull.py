#!/usr/bin/env python3
"""Unified data pull runner with state management and resilience.

This script provides a single entry point for all data collection with:
- Resumable pulls (state saved on interrupt)
- Robust error handling and retries
- Configurable data sources
- Progress tracking and logging

Usage:
    python scripts/pull.py                           # Run with default config
    python scripts/pull.py --config sample           # Use sample preset
    python scripts/pull.py --config full             # Use full preset
    python scripts/pull.py --config path/to/config.yaml
    python scripts/pull.py --status                  # Show current progress
    python scripts/pull.py --reset                   # Reset state for fresh start
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from logging_config import setup_logging, log_progress, log_error_with_context
from pull_config import PullConfig, get_sample_config, get_full_config, get_dev_config
from pull_state import StateManager
from credentials import require_valid_environment, validate_environment
from network import CircuitBreaker


def load_config(config_arg: str | None) -> PullConfig:
    """Load configuration from argument."""
    if config_arg is None or config_arg == "sample":
        return get_sample_config()
    elif config_arg == "full":
        return get_full_config()
    elif config_arg == "dev":
        return get_dev_config()
    else:
        # Treat as file path
        config_path = Path(config_arg)
        if not config_path.exists():
            # Try artifacts/configs/
            config_path = Path("artifacts/configs") / f"{config_arg}.yaml"
        if config_path.suffix in (".yaml", ".yml"):
            return PullConfig.from_yaml(config_path)
        elif config_path.suffix == ".json":
            return PullConfig.from_json(config_path)
        else:
            raise ValueError(f"Unknown config format: {config_path}")


class PullRunner:
    """Orchestrates the data pull operation."""

    def __init__(self, config: PullConfig):
        self.config = config
        self.logger, self.progress_handler = setup_logging(
            name="wiki_pull",
            log_dir=config.log_dir,
            console=True,
            json_format=False,
        )
        self.state_manager = StateManager(
            state_file=config.state_file,
            checkpoint_interval=config.checkpoint_interval,
        )
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60.0,
        )
        self._shutdown_requested = False

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _handle_shutdown(self, signum: int, frame) -> None:
        """Handle shutdown signal gracefully."""
        if self._shutdown_requested:
            self.logger.warning("Force shutdown requested")
            sys.exit(1)

        self._shutdown_requested = True
        self.logger.info("Shutdown requested, saving state...")
        self.state_manager.pause()
        self.logger.info("State saved. Run again to resume.")
        sys.exit(0)

    def run(self) -> None:
        """Run the data pull."""
        self.logger.info(f"Starting pull: {self.config.name}")
        self.logger.info(f"Description: {self.config.description}")

        if self.config.dry_run:
            self.logger.info("DRY RUN - no data will be fetched")
            self._print_plan()
            return

        # Get cases to process
        cases = self.config.get_cases()
        if not cases:
            self.logger.warning("No cases to process")
            return

        self.logger.info(f"Cases to process: {len(cases)}")

        # Initialize sources
        if self.config.arbitration.enabled:
            self.state_manager.init_source("arbitration", cases)
        if self.config.drn.enabled:
            self.state_manager.init_source("drn", cases)
        if self.config.lifecycle.enabled:
            self.state_manager.init_source("lifecycle", cases)

        # Process each source
        try:
            if self.config.arbitration.enabled:
                self._process_arbitration(cases)

            if self._shutdown_requested:
                return

            if self.config.drn.enabled:
                self._process_drn(cases)

            if self._shutdown_requested:
                return

            if self.config.lifecycle.enabled:
                self._process_lifecycle(cases)

            self.state_manager.complete()
            self.logger.info("Pull completed successfully")
            self._print_summary()

        except Exception as e:
            log_error_with_context(self.logger, "Pull failed", e)
            self.state_manager.pause()
            raise

    def _process_arbitration(self, cases: list[str]) -> None:
        """Process arbitration cases."""
        self.logger.info("Processing arbitration cases...")
        source_config = self.config.arbitration

        # Import here to avoid circular imports
        from fetchers import fetch_arbitration_case
        from wiki import WikiClient

        client = WikiClient()
        pending = self.state_manager.get_pending_items("arbitration")

        for i, case_name in enumerate(cases):
            if self._shutdown_requested:
                break
            if case_name not in pending:
                continue

            log_progress(
                self.logger,
                i + 1,
                len(cases),
                "cases",
                f"Current: {case_name}",
            )

            self.state_manager.start_item("arbitration", case_name)

            try:
                # Fetch case data
                result = fetch_arbitration_case(
                    client,
                    case_name,
                    revision_limit=source_config.revision_limit,
                    max_talk_pages=source_config.max_talk_pages,
                )

                # Save to file
                output_path = (
                    Path(self.config.output_dir)
                    / "arbitration"
                    / f"{self._safe_filename(case_name)}.json"
                )
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "w") as f:
                    json.dump(result, f, indent=2, default=str)

                self.state_manager.complete_item(
                    "arbitration",
                    case_name,
                    {"output_file": str(output_path)},
                )

            except Exception as e:
                log_error_with_context(
                    self.logger,
                    f"Failed to fetch arbitration case: {case_name}",
                    e,
                )
                self.state_manager.fail_item("arbitration", case_name, str(e))

    def _process_drn(self, cases: list[str]) -> None:
        """Process DRN cases."""
        self.logger.info("Processing DRN cases...")
        # Similar implementation to arbitration
        # TODO: Implement when DRN fetching is available
        pass

    def _process_lifecycle(self, cases: list[str]) -> None:
        """Process full lifecycle data."""
        self.logger.info("Processing lifecycle data...")
        source_config = self.config.lifecycle

        # Import here
        from lifecycle import collect_dispute_lifecycle
        from wiki import WikiClient

        client = WikiClient()
        pending = self.state_manager.get_pending_items("lifecycle")

        for i, case_name in enumerate(cases):
            if self._shutdown_requested:
                break
            if case_name not in pending:
                continue

            log_progress(
                self.logger,
                i + 1,
                len(cases),
                "cases",
                f"Current: {case_name}",
            )

            self.state_manager.start_item("lifecycle", case_name)

            try:
                result = collect_dispute_lifecycle(
                    client,
                    case_name,
                    revision_limit=source_config.revision_limit,
                )

                output_path = (
                    Path(self.config.output_dir)
                    / "dispute_venues"
                    / f"{self._safe_filename(case_name)}_lifecycle.json"
                )
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "w") as f:
                    json.dump(result, f, indent=2, default=str)

                self.state_manager.complete_item(
                    "lifecycle",
                    case_name,
                    {"output_file": str(output_path)},
                )

            except Exception as e:
                log_error_with_context(
                    self.logger,
                    f"Failed to fetch lifecycle: {case_name}",
                    e,
                )
                self.state_manager.fail_item("lifecycle", case_name, str(e))

    def _safe_filename(self, name: str) -> str:
        """Convert a name to a safe filename."""
        return name.replace("/", "_").replace("\\", "_").replace(":", "_")

    def _print_plan(self) -> None:
        """Print what would be fetched (dry run)."""
        cases = self.config.get_cases()
        print("\n=== Dry Run Plan ===")
        print(f"Config: {self.config.name}")
        print(f"Cases: {len(cases)}")

        if self.config.arbitration.enabled:
            print("\nArbitration:")
            print(f"  - Cases: {len(cases)}")
            print(f"  - Revision limit: {self.config.arbitration.revision_limit}")
            print(f"  - Max talk pages: {self.config.arbitration.max_talk_pages}")

        if self.config.drn.enabled:
            print("\nDRN:")
            print("  - Enabled: yes")

        if self.config.lifecycle.enabled:
            print("\nLifecycle:")
            print(f"  - Cases: {len(cases)}")
            print(f"  - Revision limit: {self.config.lifecycle.revision_limit}")

        print("\nCases to process:")
        for case in cases[:10]:
            print(f"  - {case}")
        if len(cases) > 10:
            print(f"  ... and {len(cases) - 10} more")

    def _print_summary(self) -> None:
        """Print final summary."""
        summary = self.state_manager.get_summary()
        print("\n=== Pull Summary ===")
        print(f"Status: {summary['status']}")
        print(f"Started: {summary['started_at']}")
        print(f"Finished: {summary['last_updated']}")

        print("\nSources:")
        for name, source in summary["sources"].items():
            print(f"  {name}:")
            print(f"    Completed: {source['completed']}/{source['total']}")
            print(f"    Failed: {source['failed']}")
            print(f"    Skipped: {source['skipped']}")

        if self.progress_handler:
            stats = self.progress_handler.get_summary()
            print("\nStatistics:")
            print(f"  API calls: {stats['api_calls']}")
            print(f"  Runtime: {stats['runtime_seconds']:.1f}s")
            print(f"  Errors: {stats['errors']}")
            print(f"  Retries: {stats['retries']}")


def show_status(config: PullConfig) -> None:
    """Show current pull status."""
    state_manager = StateManager(state_file=config.state_file)
    summary = state_manager.get_summary()

    print("=== Pull Status ===")
    print(f"Config: {config.name}")
    print(f"Status: {summary['status']}")
    print(f"Started: {summary['started_at']}")
    print(f"Last updated: {summary['last_updated']}")

    if summary["current"]:
        print(f"Current: {summary['current']}")

    print("\nProgress:")
    for name, source in summary["sources"].items():
        print(
            f"  {name}: {source['completed']}/{source['total']} ({source['progress']})"
        )

    print(f"\nErrors: {summary['total_errors']}")
    print(f"Retries: {summary['total_retries']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unified Wikipedia data pull runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--config",
        "-c",
        help="Config preset (sample, full, dev) or path to config file",
        default="sample",
    )
    parser.add_argument(
        "--status",
        "-s",
        action="store_true",
        help="Show current pull status",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset state for fresh start",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be fetched without fetching",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate environment without fetching",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip environment validation",
    )

    args = parser.parse_args()

    # Load config
    try:
        config = load_config(args.config)
    except Exception as e:
        print(f"Failed to load config: {e}", file=sys.stderr)
        sys.exit(1)

    # Handle validation
    if args.validate:
        result = validate_environment(skip_api_test=False, skip_auth_test=False)
        print(str(result))
        sys.exit(0 if result.valid else 1)

    # Handle status
    if args.status:
        show_status(config)
        sys.exit(0)

    # Handle reset
    if args.reset:
        state_manager = StateManager(state_file=config.state_file)
        state_manager.reset()
        print(f"State reset: {config.state_file}")
        sys.exit(0)

    # Apply dry-run from command line
    if args.dry_run:
        config.dry_run = True

    # Validate environment (unless skipped or dry run)
    if not args.skip_validation and not config.dry_run:
        try:
            require_valid_environment(skip_api_test=False, skip_auth_test=True)
        except EnvironmentError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)

    # Run the pull
    runner = PullRunner(config)
    try:
        runner.run()
    except KeyboardInterrupt:
        print("\nInterrupted. State saved.")
        sys.exit(130)
    except Exception as e:
        print(f"Pull failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
