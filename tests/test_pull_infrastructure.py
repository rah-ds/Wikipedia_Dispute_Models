"""Tests for pull infrastructure modules."""

from __future__ import annotations

import json
import logging
from pathlib import Path


# Import modules to test
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from logging_config import (
    setup_logging,
    get_logger,
    JsonFormatter,
    PullProgressHandler,
)
from network import (
    CircuitBreaker,
    CircuitState,
    CircuitOpenError,
    RetryConfig,
    calculate_backoff,
    is_rate_limit_error,
)
from pull_config import (
    PullConfig,
    get_sample_config,
    get_full_config,
    get_dev_config,
)
from pull_state import (
    PullState,
    StateManager,
)


class TestLoggingConfig:
    """Tests for logging configuration."""

    def test_setup_logging_returns_logger(self):
        logger, progress = setup_logging(name="test", console=True, log_dir=None)
        assert logger is not None
        assert logger.name == "test"
        assert progress is None  # No progress handler without log_dir

    def test_setup_logging_with_log_dir(self, tmp_path):
        logger, progress = setup_logging(
            name="test_file",
            console=False,
            log_dir=tmp_path,
        )
        assert logger is not None
        assert progress is not None
        assert isinstance(progress, PullProgressHandler)

    def test_get_logger_creates_child(self):
        parent, _ = setup_logging(name="wiki_disputes", console=True, log_dir=None)
        child = get_logger("test_child")
        assert child.name == "wiki_disputes.test_child"

    def test_json_formatter(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "INFO"
        assert data["message"] == "Test message"
        assert "timestamp" in data

    def test_progress_handler_tracks_stats(self):
        handler = PullProgressHandler()

        # Simulate log messages
        record1 = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Fetching page",
            args=(),
            exc_info=None,
        )
        handler.emit(record1)

        record2 = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="Error occurred",
            args=(),
            exc_info=None,
        )
        handler.emit(record2)

        summary = handler.get_summary()
        assert summary["api_calls"] == 1
        assert summary["errors"] == 1
        assert "runtime_seconds" in summary


class TestCircuitBreaker:
    """Tests for circuit breaker pattern."""

    def test_initial_state_is_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute()

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(failure_threshold=3)

        for _ in range(3):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN
        assert not cb.can_execute()

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3)

        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()

        # Should still be closed - success reset the count
        assert cb.state == CircuitState.CLOSED

    def test_get_wait_time(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=60.0)
        cb.record_failure()

        wait_time = cb.get_wait_time()
        assert 0 < wait_time <= 60.0

    def test_circuit_open_error(self):
        error = CircuitOpenError(30.0)
        assert error.wait_time == 30.0
        assert "30.0" in str(error)


class TestRetryConfig:
    """Tests for retry configuration."""

    def test_default_config(self):
        config = RetryConfig()
        assert config.max_retries == 10
        assert config.base_delay == 2.0

    def test_calculate_backoff_increases(self):
        config = RetryConfig(base_delay=1.0, max_delay=100.0, jitter=0.0)

        delay0 = calculate_backoff(0, config)
        delay1 = calculate_backoff(1, config)
        delay2 = calculate_backoff(2, config)

        assert delay1 > delay0
        assert delay2 > delay1

    def test_calculate_backoff_caps_at_max(self):
        config = RetryConfig(base_delay=1.0, max_delay=10.0, jitter=0.0)

        delay = calculate_backoff(100, config)  # Very high attempt
        assert delay <= 10.0 * 1.5  # Allow for jitter

    def test_is_rate_limit_error(self):
        config = RetryConfig()

        assert is_rate_limit_error(Exception("ratelimit exceeded"), config)
        assert is_rate_limit_error(Exception("429 Too Many Requests"), config)
        assert not is_rate_limit_error(Exception("not found"), config)


class TestPullConfig:
    """Tests for pull configuration."""

    def test_default_config(self):
        config = PullConfig()
        assert config.name == "default"
        assert config.resume_enabled

    def test_sample_config(self):
        config = get_sample_config()
        assert config.name == "sample"
        assert len(config.case_list) == 5
        assert config.arbitration.enabled
        assert config.arbitration.limit == 5

    def test_full_config(self):
        config = get_full_config()
        assert config.name == "full"
        assert config.arbitration.limit is None  # No limit

    def test_dev_config(self):
        config = get_dev_config()
        assert config.name == "dev"
        assert config.verbose

    def test_config_to_yaml(self, tmp_path):
        config = get_sample_config()
        yaml_path = tmp_path / "test.yaml"
        config.to_yaml(yaml_path)

        assert yaml_path.exists()

        # Load it back
        loaded = PullConfig.from_yaml(yaml_path)
        assert loaded.name == config.name

    def test_config_to_json(self, tmp_path):
        config = get_sample_config()
        json_path = tmp_path / "test.json"
        config.to_json(json_path)

        assert json_path.exists()

        loaded = PullConfig.from_json(json_path)
        assert loaded.name == config.name

    def test_get_cases_from_list(self):
        config = PullConfig(case_list=["Case1", "Case2", "Case3"])
        cases = config.get_cases()
        assert cases == ["Case1", "Case2", "Case3"]

    def test_get_cases_with_limit(self):
        config = PullConfig(
            case_list=["Case1", "Case2", "Case3"],
            case_limit=2,
        )
        cases = config.get_cases()
        assert cases == ["Case1", "Case2"]

    def test_get_cases_from_file(self, tmp_path):
        case_file = tmp_path / "cases.txt"
        case_file.write_text("CaseA\nCaseB\n# Comment\nCaseC\n")

        config = PullConfig(case_file=str(case_file))
        cases = config.get_cases()

        assert "CaseA" in cases
        assert "CaseB" in cases
        assert "CaseC" in cases
        assert "# Comment" not in cases


class TestPullState:
    """Tests for pull state management."""

    def test_state_creation(self):
        state = PullState()
        assert state.status == "not_started"
        assert state.started_at

    def test_state_to_dict(self):
        state = PullState(config_name="test")
        data = state.to_dict()
        assert data["config_name"] == "test"
        assert "sources" in data

    def test_state_from_dict(self):
        data = {
            "config_name": "test",
            "status": "in_progress",
            "started_at": "2024-01-01T00:00:00Z",
            "last_updated": "2024-01-01T00:00:00Z",
            "sources": {},
            "version": 1,
            "current_source": None,
            "current_item": None,
            "total_api_calls": 0,
            "total_errors": 0,
            "total_retries": 0,
        }
        state = PullState.from_dict(data)
        assert state.config_name == "test"
        assert state.status == "in_progress"


class TestStateManager:
    """Tests for state manager."""

    def test_load_or_create_new(self, tmp_path):
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file)

        state = manager.load_or_create()
        assert state.status == "not_started"

    def test_save_and_load(self, tmp_path):
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file, checkpoint_interval=1)

        manager.state.config_name = "test"
        manager.save(force=True)

        # Create new manager and load
        manager2 = StateManager(state_file)
        state = manager2.load_or_create()
        assert state.config_name == "test"

    def test_init_source(self, tmp_path):
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file, checkpoint_interval=1)

        manager.init_source("arbitration", ["Case1", "Case2", "Case3"])

        assert "arbitration" in manager.state.sources
        source = manager.state.sources["arbitration"]
        assert source.total_items == 3

    def test_start_and_complete_item(self, tmp_path):
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file, checkpoint_interval=1)

        manager.init_source("test", ["Item1"])
        manager.start_item("test", "Item1")

        assert manager.state.current_item == "Item1"
        assert manager.state.sources["test"].items["Item1"].status == "in_progress"

        manager.complete_item("test", "Item1")
        assert manager.state.sources["test"].items["Item1"].status == "completed"
        assert manager.state.sources["test"].completed_items == 1

    def test_fail_item(self, tmp_path):
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file, checkpoint_interval=1)

        manager.init_source("test", ["Item1"])
        manager.start_item("test", "Item1")
        manager.fail_item("test", "Item1", "Network error")

        item = manager.state.sources["test"].items["Item1"]
        assert item.status == "failed"
        assert item.error == "Network error"
        assert manager.state.total_errors == 1

    def test_should_process(self, tmp_path):
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file, checkpoint_interval=1)

        manager.init_source("test", ["Item1", "Item2"])

        # Both should need processing
        assert manager.should_process("test", "Item1")
        assert manager.should_process("test", "Item2")

        # Complete one
        manager.complete_item("test", "Item1")

        # Only Item2 should need processing
        assert not manager.should_process("test", "Item1")
        assert manager.should_process("test", "Item2")

    def test_get_pending_items(self, tmp_path):
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file, checkpoint_interval=1)

        manager.init_source("test", ["Item1", "Item2", "Item3"])
        manager.complete_item("test", "Item1")
        manager.skip_item("test", "Item2", "reason")

        pending = manager.get_pending_items("test")
        assert "Item3" in pending
        assert "Item1" not in pending
        assert "Item2" not in pending

    def test_get_summary(self, tmp_path):
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file, checkpoint_interval=1)

        manager.init_source("arbitration", ["Case1", "Case2"])
        manager.complete_item("arbitration", "Case1")

        summary = manager.get_summary()
        assert summary["status"] == "not_started"
        assert "arbitration" in summary["sources"]
        assert summary["sources"]["arbitration"]["completed"] == 1

    def test_pause_and_resume(self, tmp_path):
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file, checkpoint_interval=1)

        manager.init_source("test", ["Item1", "Item2"])
        manager.start_item("test", "Item1")
        manager.pause()

        assert manager.state.status == "paused"

        # Simulate resume with new manager
        manager2 = StateManager(state_file)
        state = manager2.load_or_create()
        assert state.status == "paused"
        assert "test" in state.sources
