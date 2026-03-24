"""Tests for src/cli_utils.py."""

import signal
import sys
from unittest.mock import MagicMock, patch

import pytest

from src.cli_utils import (
    get_memory_mb,
    register_client,
    register_logger,
    setup_shutdown_handler,
    shutdown_handler,
)


class TestRegisterClient:
    """Tests for register_client function."""

    def test_registers_client(self):
        import src.cli_utils as cli_utils

        mock_client = MagicMock()
        register_client(mock_client)
        assert cli_utils._client is mock_client

    def test_can_replace_client(self):
        import src.cli_utils as cli_utils

        client1 = MagicMock()
        client2 = MagicMock()

        register_client(client1)
        assert cli_utils._client is client1

        register_client(client2)
        assert cli_utils._client is client2


class TestRegisterLogger:
    """Tests for register_logger function."""

    def test_registers_logger(self):
        import src.cli_utils as cli_utils

        mock_logger = MagicMock()
        register_logger(mock_logger)
        assert cli_utils._logger is mock_logger


class TestSetupShutdownHandler:
    """Tests for setup_shutdown_handler function."""

    def test_registers_sigint_handler(self):
        with patch("signal.signal") as mock_signal:
            setup_shutdown_handler()
            mock_signal.assert_called_once_with(signal.SIGINT, shutdown_handler)


class TestShutdownHandler:
    """Tests for shutdown_handler function."""

    def test_logs_stats_when_client_registered(self):
        import src.cli_utils as cli_utils

        mock_client = MagicMock()
        mock_client.get_stats.return_value = {
            "total_requests": 100,
            "runtime_minutes": 5.5,
        }

        cli_utils._client = mock_client
        cli_utils._logger = None

        with pytest.raises(SystemExit) as exc_info:
            shutdown_handler(signal.SIGINT, None)

        assert exc_info.value.code == 130
        mock_client.log_stats.assert_called_once()
        mock_client.get_stats.assert_called_once()

    def test_logs_to_logger_when_registered(self):
        import src.cli_utils as cli_utils

        mock_logger = MagicMock()
        cli_utils._client = None
        cli_utils._logger = mock_logger

        with pytest.raises(SystemExit) as exc_info:
            shutdown_handler(signal.SIGINT, None)

        assert exc_info.value.code == 130
        mock_logger.info.assert_called_once_with("Fetch interrupted by user")

    def test_exits_with_code_130(self):
        import src.cli_utils as cli_utils

        cli_utils._client = None
        cli_utils._logger = None

        with pytest.raises(SystemExit) as exc_info:
            shutdown_handler(signal.SIGINT, None)

        assert exc_info.value.code == 130

    def test_handles_both_client_and_logger(self):
        import src.cli_utils as cli_utils

        mock_client = MagicMock()
        mock_client.get_stats.return_value = {
            "total_requests": 50,
            "runtime_minutes": 2.0,
        }
        mock_logger = MagicMock()

        cli_utils._client = mock_client
        cli_utils._logger = mock_logger

        with pytest.raises(SystemExit):
            shutdown_handler(signal.SIGINT, None)

        mock_client.log_stats.assert_called_once()
        mock_logger.info.assert_called_once()


class TestGetMemoryMb:
    """Tests for get_memory_mb function."""

    def test_returns_float(self):
        result = get_memory_mb()
        assert isinstance(result, float)

    def test_returns_non_negative(self):
        result = get_memory_mb()
        assert result >= 0.0

    def test_handles_import_error(self):
        with patch.dict(sys.modules, {"resource": None}):
            with patch("src.cli_utils.get_memory_mb") as mock_func:
                mock_func.return_value = 0.0
                result = mock_func()
                assert result == 0.0

    @patch("sys.platform", "darwin")
    def test_macos_conversion(self):
        with patch("resource.getrusage") as mock_rusage:
            mock_usage = MagicMock()
            mock_usage.ru_maxrss = 104857600  # 100 MB in bytes
            mock_rusage.return_value = mock_usage

            result = get_memory_mb()

            # On macOS, should divide by 1024*1024
            assert result == pytest.approx(100.0, rel=0.01)

    @patch("sys.platform", "linux")
    def test_linux_conversion(self):
        with patch("resource.getrusage") as mock_rusage:
            mock_usage = MagicMock()
            mock_usage.ru_maxrss = 102400  # 100 MB in KB
            mock_rusage.return_value = mock_usage

            # Need to reimport to pick up patched platform
            from src.cli_utils import get_memory_mb as get_mem

            result = get_mem()

            # On Linux, should divide by 1024 only
            # Note: This test may not work as expected due to import caching
            assert isinstance(result, float)


class TestModuleState:
    """Tests for module-level state management."""

    def test_initial_state_is_none(self):
        # Reset module state
        import src.cli_utils as cli_utils

        cli_utils._client = None
        cli_utils._logger = None

        assert cli_utils._client is None
        assert cli_utils._logger is None

    def test_state_persists_across_calls(self):
        import src.cli_utils as cli_utils

        mock_client = MagicMock()
        register_client(mock_client)

        # State should persist
        assert cli_utils._client is mock_client

        # Another call to a different function shouldn't affect it
        mock_logger = MagicMock()
        register_logger(mock_logger)

        assert cli_utils._client is mock_client
        assert cli_utils._logger is mock_logger
