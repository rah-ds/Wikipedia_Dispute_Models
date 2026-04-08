"""State management for resumable data pulls.

Tracks progress through data collection to enable resume after
interruption or failure.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ItemProgress:
    """Progress for a single item (case, page, etc.)."""

    name: str
    status: str = "pending"  # pending, in_progress, completed, failed, skipped
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    retries: int = 0
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceProgress:
    """Progress for a data source (arbitration, drn, etc.)."""

    name: str
    enabled: bool = True
    total_items: int = 0
    completed_items: int = 0
    failed_items: int = 0
    skipped_items: int = 0
    items: dict[str, ItemProgress] = field(default_factory=dict)

    @property
    def progress_pct(self) -> float:
        if self.total_items == 0:
            return 0.0
        return (self.completed_items / self.total_items) * 100


@dataclass
class PullState:
    """Complete state for a data pull operation."""

    # Metadata
    config_name: str = ""
    config_path: str | None = None
    started_at: str = ""
    last_updated: str = ""
    version: int = 1

    # Overall status
    status: str = "not_started"  # not_started, in_progress, completed, failed, paused
    current_source: str | None = None
    current_item: str | None = None

    # Sources
    sources: dict[str, SourceProgress] = field(default_factory=dict)

    # Statistics
    total_api_calls: int = 0
    total_errors: int = 0
    total_retries: int = 0

    def __post_init__(self) -> None:
        if not self.started_at:
            self.started_at = datetime.utcnow().isoformat() + "Z"
        self.last_updated = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = asdict(self)
        # Convert nested dataclasses
        result["sources"] = {
            name: asdict(source) for name, source in self.sources.items()
        }
        for source_data in result["sources"].values():
            source_data["items"] = {
                name: asdict(item) if isinstance(item, ItemProgress) else item
                for name, item in source_data["items"].items()
            }
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PullState":
        """Create from dictionary."""
        # Convert nested dicts to dataclasses
        sources = {}
        for name, source_data in data.get("sources", {}).items():
            items = {
                item_name: ItemProgress(**item_data)
                for item_name, item_data in source_data.get("items", {}).items()
            }
            source_data["items"] = items
            sources[name] = SourceProgress(**source_data)
        data["sources"] = sources
        return cls(**data)


class StateManager:
    """Manages pull state persistence and updates."""

    def __init__(self, state_file: str | Path, checkpoint_interval: int = 10):
        self.state_file = Path(state_file)
        self.checkpoint_interval = checkpoint_interval
        self._state: PullState | None = None
        self._changes_since_save = 0

    @property
    def state(self) -> PullState:
        if self._state is None:
            self._state = self.load_or_create()
        return self._state

    def load_or_create(self) -> PullState:
        """Load existing state or create new."""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    data = json.load(f)
                state = PullState.from_dict(data)
                logger.info(f"Loaded existing state from {self.state_file}")
                logger.info(f"  Status: {state.status}")
                logger.info(f"  Started: {state.started_at}")
                return state
            except Exception as e:
                logger.warning(f"Failed to load state file: {e}")
                logger.info("Starting fresh")

        return PullState()

    def save(self, force: bool = False) -> None:
        """Save state to file."""
        if self._state is None:
            return

        self._state.last_updated = datetime.utcnow().isoformat() + "Z"

        # Only save on checkpoint interval unless forced
        self._changes_since_save += 1
        if not force and self._changes_since_save < self.checkpoint_interval:
            return

        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(self._state.to_dict(), f, indent=2)

        self._changes_since_save = 0
        logger.debug(f"State saved to {self.state_file}")

    def init_source(
        self,
        source_name: str,
        items: list[str],
        enabled: bool = True,
    ) -> None:
        """Initialize a data source with items to process."""
        source = SourceProgress(
            name=source_name,
            enabled=enabled,
            total_items=len(items),
        )

        # Check for existing progress
        if source_name in self.state.sources:
            existing = self.state.sources[source_name]
            # Merge existing item progress
            for item_name in items:
                if item_name in existing.items:
                    source.items[item_name] = existing.items[item_name]
                    if existing.items[item_name].status == "completed":
                        source.completed_items += 1
                    elif existing.items[item_name].status == "failed":
                        source.failed_items += 1
                else:
                    source.items[item_name] = ItemProgress(name=item_name)
        else:
            for item_name in items:
                source.items[item_name] = ItemProgress(name=item_name)

        self.state.sources[source_name] = source
        self.save()

    def start_item(self, source_name: str, item_name: str) -> None:
        """Mark an item as started."""
        self.state.current_source = source_name
        self.state.current_item = item_name
        self.state.status = "in_progress"

        if source_name in self.state.sources:
            source = self.state.sources[source_name]
            if item_name not in source.items:
                source.items[item_name] = ItemProgress(name=item_name)
            source.items[item_name].status = "in_progress"
            source.items[item_name].started_at = datetime.utcnow().isoformat() + "Z"

        self.save()

    def complete_item(
        self,
        source_name: str,
        item_name: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Mark an item as completed."""
        if source_name in self.state.sources:
            source = self.state.sources[source_name]
            if item_name in source.items:
                item = source.items[item_name]
                item.status = "completed"
                item.completed_at = datetime.utcnow().isoformat() + "Z"
                if data:
                    item.data = data
                source.completed_items += 1

        self.save()

    def fail_item(
        self,
        source_name: str,
        item_name: str,
        error: str,
    ) -> None:
        """Mark an item as failed."""
        if source_name in self.state.sources:
            source = self.state.sources[source_name]
            if item_name in source.items:
                item = source.items[item_name]
                item.status = "failed"
                item.completed_at = datetime.utcnow().isoformat() + "Z"
                item.error = error
                item.retries += 1
                source.failed_items += 1

        self.state.total_errors += 1
        self.save()

    def skip_item(self, source_name: str, item_name: str, reason: str = "") -> None:
        """Mark an item as skipped."""
        if source_name in self.state.sources:
            source = self.state.sources[source_name]
            if item_name in source.items:
                source.items[item_name].status = "skipped"
                source.items[item_name].error = reason
                source.skipped_items += 1

        self.save()

    def should_process(self, source_name: str, item_name: str) -> bool:
        """Check if an item should be processed (not already completed)."""
        if source_name not in self.state.sources:
            return True
        source = self.state.sources[source_name]
        if item_name not in source.items:
            return True
        return source.items[item_name].status not in ("completed", "skipped")

    def get_pending_items(self, source_name: str) -> list[str]:
        """Get list of items that still need processing."""
        if source_name not in self.state.sources:
            return []
        source = self.state.sources[source_name]
        return [
            name
            for name, item in source.items.items()
            if item.status in ("pending", "in_progress", "failed")
        ]

    def get_summary(self) -> dict[str, Any]:
        """Get summary of current progress."""
        sources_summary = {}
        for name, source in self.state.sources.items():
            sources_summary[name] = {
                "total": source.total_items,
                "completed": source.completed_items,
                "failed": source.failed_items,
                "skipped": source.skipped_items,
                "progress": f"{source.progress_pct:.1f}%",
            }

        return {
            "status": self.state.status,
            "started_at": self.state.started_at,
            "last_updated": self.state.last_updated,
            "current": f"{self.state.current_source}/{self.state.current_item}"
            if self.state.current_source
            else None,
            "sources": sources_summary,
            "total_errors": self.state.total_errors,
            "total_retries": self.state.total_retries,
        }

    def complete(self) -> None:
        """Mark the entire pull as completed."""
        self.state.status = "completed"
        self.state.current_source = None
        self.state.current_item = None
        self.save(force=True)

    def pause(self) -> None:
        """Mark the pull as paused (for resume later)."""
        self.state.status = "paused"
        self.save(force=True)

    def reset(self) -> None:
        """Reset state for a fresh start."""
        self._state = PullState()
        self.save(force=True)
