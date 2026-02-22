"""Pull configuration for Wikipedia data collection.

Provides configurable data pull settings for sample, full,
and custom collection runs.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""

    requests_per_second: float = 5.0
    burst_size: int = 10
    min_delay_between_requests: float = 0.1  # seconds


@dataclass
class RetryConfig:
    """Retry behavior configuration."""

    max_retries: int = 10
    base_delay: float = 2.0
    max_delay: float = 300.0
    exponential_base: float = 2.0


@dataclass
class DataSourceConfig:
    """Configuration for a specific data source."""

    enabled: bool = True
    limit: int | None = None  # None = no limit
    include_revisions: bool = True
    revision_limit: int | None = 100
    include_talk_pages: bool = True
    max_talk_pages: int | None = 50


@dataclass
class PullConfig:
    """Complete configuration for a data pull operation."""

    # Basic settings
    name: str = "default"
    description: str = ""
    output_dir: str = "data/raw"
    log_dir: str = "artifacts/logs/data_pull"

    # State management
    state_file: str = "artifacts/pull_state.json"
    resume_enabled: bool = True
    checkpoint_interval: int = 10  # Save state every N items

    # Rate limiting
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)

    # Data sources
    arbitration: DataSourceConfig = field(default_factory=DataSourceConfig)
    drn: DataSourceConfig = field(default_factory=DataSourceConfig)
    ani: DataSourceConfig = field(default_factory=DataSourceConfig)
    talk_pages: DataSourceConfig = field(default_factory=DataSourceConfig)
    lifecycle: DataSourceConfig = field(default_factory=DataSourceConfig)

    # Case selection
    case_file: str | None = None  # Path to list of cases
    case_list: list[str] = field(default_factory=list)  # Explicit case list
    case_limit: int | None = None  # Limit number of cases

    # Feature flags
    fetch_user_info: bool = False
    fetch_block_history: bool = False
    fetch_edit_tags: bool = False
    dry_run: bool = False
    verbose: bool = False

    @classmethod
    def from_yaml(cls, path: str | Path) -> "PullConfig":
        """Load configuration from a YAML file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path) as f:
            data = yaml.safe_load(f)

        return cls._from_dict(data)

    @classmethod
    def from_json(cls, path: str | Path) -> "PullConfig":
        """Load configuration from a JSON file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path) as f:
            data = json.load(f)

        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "PullConfig":
        """Create config from dictionary."""
        # Handle nested configs
        if "rate_limit" in data and isinstance(data["rate_limit"], dict):
            data["rate_limit"] = RateLimitConfig(**data["rate_limit"])
        if "retry" in data and isinstance(data["retry"], dict):
            data["retry"] = RetryConfig(**data["retry"])

        for source in ["arbitration", "drn", "ani", "talk_pages", "lifecycle"]:
            if source in data and isinstance(data[source], dict):
                data[source] = DataSourceConfig(**data[source])

        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return asdict(self)

    def to_yaml(self, path: str | Path) -> None:
        """Save configuration to YAML file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            yaml.safe_dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)

    def to_json(self, path: str | Path) -> None:
        """Save configuration to JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    def get_cases(self) -> list[str]:
        """Get list of cases to process."""
        cases = list(self.case_list)

        # Load from file if specified
        if self.case_file:
            case_path = Path(self.case_file)
            if case_path.exists():
                with open(case_path) as f:
                    file_cases = [
                        line.strip()
                        for line in f
                        if line.strip() and not line.startswith("#")
                    ]
                    cases.extend(file_cases)

        # Apply limit if specified
        if self.case_limit is not None and self.case_limit > 0:
            cases = cases[: self.case_limit]

        return cases


# Preset configurations
def get_sample_config() -> PullConfig:
    """Get configuration for a small sample pull."""
    return PullConfig(
        name="sample",
        description="Small sample for testing (5 cases, limited revisions)",
        case_list=[
            "Climate change",
            "Gamergate",
            "Eastern Europe",
            "Scientology",
            "Muhammad images",
        ],
        arbitration=DataSourceConfig(
            enabled=True,
            limit=5,
            revision_limit=50,
            max_talk_pages=10,
        ),
        drn=DataSourceConfig(
            enabled=True,
            limit=10,
            revision_limit=50,
        ),
        ani=DataSourceConfig(enabled=False),
        lifecycle=DataSourceConfig(
            enabled=True,
            limit=5,
            revision_limit=50,
        ),
    )


def get_full_config() -> PullConfig:
    """Get configuration for a full data pull."""
    return PullConfig(
        name="full",
        description="Full data collection (all cases, all revisions)",
        case_file="artifacts/arb_cases.txt",
        arbitration=DataSourceConfig(
            enabled=True,
            limit=None,
            revision_limit=None,
            max_talk_pages=None,
        ),
        drn=DataSourceConfig(
            enabled=True,
            limit=None,
            revision_limit=None,
        ),
        ani=DataSourceConfig(enabled=True),
        lifecycle=DataSourceConfig(
            enabled=True,
            limit=None,
            revision_limit=None,
        ),
        fetch_user_info=True,
        fetch_block_history=True,
        fetch_edit_tags=True,
    )


def get_dev_config() -> PullConfig:
    """Get configuration for development/debugging."""
    return PullConfig(
        name="dev",
        description="Minimal pull for development (1 case, minimal data)",
        case_list=["Climate change"],
        arbitration=DataSourceConfig(
            enabled=True,
            limit=1,
            revision_limit=10,
            max_talk_pages=2,
        ),
        drn=DataSourceConfig(enabled=False),
        ani=DataSourceConfig(enabled=False),
        lifecycle=DataSourceConfig(enabled=False),
        verbose=True,
    )


def save_preset_configs(output_dir: str | Path = "artifacts/configs") -> None:
    """Save preset configurations to files."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    presets = {
        "sample": get_sample_config(),
        "full": get_full_config(),
        "dev": get_dev_config(),
    }

    for name, config in presets.items():
        config.to_yaml(output_dir / f"{name}.yaml")
        logger.info(f"Saved {name} config to {output_dir / f'{name}.yaml'}")
