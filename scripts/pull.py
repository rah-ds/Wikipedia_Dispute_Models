#!/usr/bin/env python3
"""Unified data pull runner with state management and resilience.

This script provides a single entry point for all data collection with:
- Resumable pulls (state saved on interrupt)
- Robust error handling and retries
- Configurable data sources
- Progress tracking with tqdm
- Timing and rate limit monitoring
- Internet speed logging

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
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# Add project root and src to path
_project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, _project_root)
sys.path.insert(0, str(Path(_project_root) / "src"))

from logging_config import setup_logging, log_error_with_context
from pull_config import PullConfig, get_sample_config, get_full_config, get_dev_config
from pull_state import StateManager
from credentials import require_valid_environment, validate_environment
from network import CircuitBreaker
from rate_tracker import (
    RateTracker,
    check_internet_speed,
    estimate_pull_capacity,
    SpeedTestResult,
)

# Try to import tqdm, fall back to simple progress if not available
try:
    from tqdm import tqdm

    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

    # Fallback for when tqdm is not installed
    class tqdm:  # type: ignore
        """Minimal tqdm fallback."""

        def __init__(self, iterable=None, total=None, desc=None, **kwargs):
            self.iterable = iterable
            self.total = total
            self.desc = desc
            self.n = 0

        def __iter__(self):
            for item in self.iterable:
                yield item
                self.n += 1

        def update(self, n=1):
            self.n += n

        def set_postfix_str(self, s):
            pass

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass


def format_duration(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins}m {secs:.0f}s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"


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
    """Orchestrates the data pull operation with timing and progress tracking."""

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

        # Timing tracking
        self.start_time: datetime | None = None
        self.case_timings: list[dict] = []
        self.source_timings: dict[str, float] = {}

        # Rate tracking
        self.rate_tracker = RateTracker.get_instance()

        # Speed test result
        self.speed_result: SpeedTestResult | None = None

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
        self._print_timing_summary()
        self.logger.info("State saved. Run again to resume.")
        sys.exit(0)

    def _check_internet_speed(self) -> None:
        """Run internet speed test and log results."""
        self.logger.info("Checking internet connection speed...")
        self.speed_result = check_internet_speed()

        if self.speed_result.success:
            self.logger.info(f"Speed test: {self.speed_result}")

            # Estimate capacity based on authentication status
            api_key = "mediawiki_auth"  # Assume authenticated for now
            capacity = estimate_pull_capacity(self.speed_result.download_mbps, api_key)

            self.logger.info(
                f"Estimated capacity: ~{capacity['estimated_cases_per_hour']} cases/hour "
                f"(limited by {capacity['limiting_factor']})"
            )
        else:
            self.logger.warning(f"Speed test failed: {self.speed_result.error}")

    def _log_rate_usage(self) -> None:
        """Log current rate limit usage."""
        summary = self.rate_tracker.get_summary()
        for line in summary.split("\n"):
            self.logger.info(line)

    def run(self) -> None:
        """Run the data pull."""
        self.start_time = datetime.now()
        self.logger.info(f"Starting pull: {self.config.name}")
        self.logger.info(f"Description: {self.config.description}")
        self.logger.info(f"Start time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")

        if self.config.dry_run:
            self.logger.info("DRY RUN - no data will be fetched")
            self._print_plan()
            return

        # Run speed test
        self._check_internet_speed()

        # Log rate limit info
        self.logger.info("Rate limits:")
        self.logger.info("  MediaWiki API (authenticated): 5,000 requests/hour")
        self.logger.info("  ORES/Lift Wing: 100 requests/second")
        self.logger.info("  Pageviews API: 100 requests/second")

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
        """Process arbitration cases with full enrichment and tqdm progress bar."""
        source_start = time.time()
        self.logger.info("Processing arbitration cases (full enrichment)...")
        source_config = self.config.arbitration

        # Import here to avoid circular imports
        from arbitration import fetch_full_arbitration_case
        from wiki import WikiClient

        client = WikiClient()
        pending = self.state_manager.get_pending_items("arbitration")
        pending_cases = [c for c in cases if c in pending]

        if not pending_cases:
            self.logger.info("All arbitration cases already completed")
            return

        # Log enrichment settings
        self.logger.info(
            f"Enrichment: participants={source_config.enrich_participants}, "
            f"articles={source_config.enrich_articles}, "
            f"max_articles={source_config.max_articles}"
        )

        # Create progress bar
        pbar_kwargs = {
            "total": len(pending_cases),
            "desc": "Arbitration",
            "unit": "case",
            "ncols": 100,
            "bar_format": "{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
        }

        if TQDM_AVAILABLE:
            pbar = tqdm(**pbar_kwargs)
        else:
            pbar = tqdm(range(len(pending_cases)), **pbar_kwargs)

        for i, case_name in enumerate(pending_cases):
            if self._shutdown_requested:
                pbar.close()
                break

            case_start = time.time()

            # Update progress bar description
            short_name = case_name[:30] + "..." if len(case_name) > 30 else case_name
            pbar.set_postfix_str(f"Current: {short_name}")

            self.state_manager.start_item("arbitration", case_name)

            try:
                # Fetch case data with full enrichment
                result = fetch_full_arbitration_case(
                    client,
                    case_name,
                    revision_limit=source_config.revision_limit or 100,
                    max_articles=source_config.max_articles,
                    enrich_participants=source_config.enrich_participants,
                    enrich_articles=source_config.enrich_articles,
                    include_ani=source_config.include_ani,
                    include_drn=source_config.include_drn,
                )

                # Record API usage (estimate based on enrichment)
                api_calls = 10  # Base calls
                if source_config.enrich_participants:
                    api_calls += result.get("summary", {}).get("participants_enriched", 0) * 2
                if source_config.enrich_articles:
                    api_calls += result.get("summary", {}).get("articles_enriched", 0) * 3
                self.rate_tracker.record("mediawiki_auth", count=api_calls)

                # Save to file
                output_path = (
                    Path(self.config.output_dir)
                    / "arbitration"
                    / f"{self._safe_filename(case_name)}.json"
                )
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "w") as f:
                    json.dump(result, f, indent=2, default=str)

                case_duration = time.time() - case_start
                self.case_timings.append(
                    {
                        "source": "arbitration",
                        "case": case_name,
                        "duration": case_duration,
                        "success": True,
                    }
                )

                self.state_manager.complete_item(
                    "arbitration",
                    case_name,
                    {
                        "output_file": str(output_path),
                        "duration_seconds": case_duration,
                    },
                )

            except Exception as e:
                case_duration = time.time() - case_start
                self.case_timings.append(
                    {
                        "source": "arbitration",
                        "case": case_name,
                        "duration": case_duration,
                        "success": False,
                        "error": str(e),
                    }
                )

                log_error_with_context(
                    self.logger,
                    f"Failed to fetch arbitration case: {case_name}",
                    e,
                )
                self.state_manager.fail_item("arbitration", case_name, str(e))

            pbar.update(1)

            # Log rate usage every 10 cases
            if (i + 1) % 10 == 0:
                rate_summary = self.rate_tracker.get_compact_summary()
                self.logger.debug(f"Rate usage: {rate_summary}")

        pbar.close()
        self.source_timings["arbitration"] = time.time() - source_start

    def _process_drn(self, cases: list[str]) -> None:
        """Process DRN cases."""
        self.logger.info("Processing DRN cases...")
        # Similar implementation to arbitration
        # TODO: Implement when DRN fetching is available
        pass

    def _process_lifecycle(self, cases: list[str]) -> None:
        """Process full lifecycle data with tqdm progress bar."""
        source_start = time.time()
        self.logger.info("Processing lifecycle data...")
        source_config = self.config.lifecycle

        # Import here
        from lifecycle import collect_dispute_lifecycle
        from wiki import WikiClient

        client = WikiClient()
        pending = self.state_manager.get_pending_items("lifecycle")
        pending_cases = [c for c in cases if c in pending]

        if not pending_cases:
            self.logger.info("All lifecycle cases already completed")
            return

        # Create progress bar
        pbar_kwargs = {
            "total": len(pending_cases),
            "desc": "Lifecycle",
            "unit": "case",
            "ncols": 100,
            "bar_format": "{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
        }

        if TQDM_AVAILABLE:
            pbar = tqdm(**pbar_kwargs)
        else:
            pbar = tqdm(range(len(pending_cases)), **pbar_kwargs)

        for i, case_name in enumerate(pending_cases):
            if self._shutdown_requested:
                pbar.close()
                break

            case_start = time.time()

            # Update progress bar
            short_name = case_name[:30] + "..." if len(case_name) > 30 else case_name
            pbar.set_postfix_str(f"Current: {short_name}")

            self.state_manager.start_item("lifecycle", case_name)

            try:
                result = collect_dispute_lifecycle(
                    client,
                    case_name,
                    revision_limit=source_config.revision_limit,
                )

                # Record API usage
                self.rate_tracker.record("mediawiki_auth", count=20)

                output_path = (
                    Path(self.config.output_dir)
                    / "dispute_venues"
                    / f"{self._safe_filename(case_name)}_lifecycle.json"
                )
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "w") as f:
                    json.dump(result, f, indent=2, default=str)

                case_duration = time.time() - case_start
                self.case_timings.append(
                    {
                        "source": "lifecycle",
                        "case": case_name,
                        "duration": case_duration,
                        "success": True,
                    }
                )

                self.state_manager.complete_item(
                    "lifecycle",
                    case_name,
                    {
                        "output_file": str(output_path),
                        "duration_seconds": case_duration,
                    },
                )

            except Exception as e:
                case_duration = time.time() - case_start
                self.case_timings.append(
                    {
                        "source": "lifecycle",
                        "case": case_name,
                        "duration": case_duration,
                        "success": False,
                        "error": str(e),
                    }
                )

                log_error_with_context(
                    self.logger,
                    f"Failed to fetch lifecycle: {case_name}",
                    e,
                )
                self.state_manager.fail_item("lifecycle", case_name, str(e))

            pbar.update(1)

            # Log rate usage every 10 cases
            if (i + 1) % 10 == 0:
                rate_summary = self.rate_tracker.get_compact_summary()
                self.logger.debug(f"Rate usage: {rate_summary}")

        pbar.close()
        self.source_timings["lifecycle"] = time.time() - source_start

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

    def _print_timing_summary(self) -> None:
        """Print timing summary for completed work."""
        if not self.start_time:
            return

        total_duration = (datetime.now() - self.start_time).total_seconds()
        print("\n=== Timing Summary ===")
        print(f"Total runtime: {format_duration(total_duration)}")

        # Source timings
        if self.source_timings:
            print("\nBy source:")
            for source, duration in self.source_timings.items():
                print(f"  {source}: {format_duration(duration)}")

        # Case statistics
        if self.case_timings:
            successful = [t for t in self.case_timings if t["success"]]
            failed = [t for t in self.case_timings if not t["success"]]

            if successful:
                durations = [t["duration"] for t in successful]
                avg_duration = sum(durations) / len(durations)
                min_duration = min(durations)
                max_duration = max(durations)

                print(f"\nCase timings (successful: {len(successful)}):")
                print(f"  Average: {format_duration(avg_duration)}")
                print(f"  Min: {format_duration(min_duration)}")
                print(f"  Max: {format_duration(max_duration)}")

            if failed:
                print(f"\nFailed cases: {len(failed)}")

    def _print_summary(self) -> None:
        """Print final summary."""
        summary = self.state_manager.get_summary()
        total_duration = (
            (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        )

        print("\n" + "=" * 60)
        print("                    PULL SUMMARY")
        print("=" * 60)

        print(f"\nStatus: {summary['status']}")
        print(f"Started: {summary['started_at']}")
        print(f"Finished: {summary['last_updated']}")
        print(f"Total runtime: {format_duration(total_duration)}")

        # Internet speed
        if self.speed_result and self.speed_result.success:
            print(f"\nInternet speed: {self.speed_result.download_mbps:.2f} Mbps")

        # Source breakdown
        print("\n--- Sources ---")
        for name, source in summary["sources"].items():
            print(f"\n{name.upper()}:")
            print(f"  Completed: {source['completed']}/{source['total']}")
            print(f"  Failed: {source['failed']}")
            print(f"  Skipped: {source['skipped']}")
            if name in self.source_timings:
                print(f"  Duration: {format_duration(self.source_timings[name])}")

        # Timing statistics
        self._print_timing_summary()

        # Rate limit usage
        print("\n--- Rate Limit Usage ---")
        self._log_rate_usage()

        # Progress handler stats
        if self.progress_handler:
            stats = self.progress_handler.get_summary()
            print("\n--- API Statistics ---")
            print(f"  Total API calls: {stats['api_calls']}")
            print(f"  Pages fetched: {stats['pages_fetched']}")
            print(f"  Errors: {stats['errors']}")
            print(f"  Retries: {stats['retries']}")
            if total_duration > 0:
                print(f"  Throughput: {stats['pages_per_minute']:.1f} pages/minute")

        print("\n" + "=" * 60)


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
    parser.add_argument(
        "--skip-speed-test",
        action="store_true",
        help="Skip internet speed test",
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

    # Check tqdm availability
    if not TQDM_AVAILABLE:
        print(
            "Note: tqdm not installed. Install with 'pip install tqdm' for progress bars.",
            file=sys.stderr,
        )

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
