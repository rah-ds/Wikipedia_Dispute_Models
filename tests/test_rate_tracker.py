"""Tests for rate tracking and internet speed monitoring."""

import sys
from pathlib import Path


# Add src to path for direct import
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rate_tracker import (
    RateLimitInfo,
    RateWindow,
    RateTracker,
    SpeedTestResult,
    check_internet_speed,
    estimate_pull_capacity,
    RATE_LIMITS,
)


class TestRateLimitInfo:
    """Tests for RateLimitInfo."""

    def test_window_display_hours(self):
        info = RateLimitInfo("test", 100, 3600, "test limit")
        assert info.window_display == "1h"

    def test_window_display_minutes(self):
        info = RateLimitInfo("test", 100, 120, "test limit")
        assert info.window_display == "2m"

    def test_window_display_seconds(self):
        info = RateLimitInfo("test", 100, 30, "test limit")
        assert info.window_display == "30s"


class TestRateWindow:
    """Tests for RateWindow."""

    def test_record_request(self):
        info = RateLimitInfo("test", 100, 60, "test")
        window = RateWindow(limit_info=info)

        window.record_request()
        assert window.current_count == 1
        assert window.total_requests == 1

    def test_record_multiple_requests(self):
        info = RateLimitInfo("test", 100, 60, "test")
        window = RateWindow(limit_info=info)

        window.record_request(count=5)
        assert window.current_count == 5
        assert window.total_requests == 5

    def test_remaining_capacity(self):
        info = RateLimitInfo("test", 100, 60, "test")
        window = RateWindow(limit_info=info)

        window.record_request(count=30)
        assert window.remaining == 70

    def test_usage_percentage(self):
        info = RateLimitInfo("test", 100, 60, "test")
        window = RateWindow(limit_info=info)

        window.record_request(count=25)
        assert window.usage_pct == 25.0

    def test_should_wait_false(self):
        info = RateLimitInfo("test", 100, 60, "test")
        window = RateWindow(limit_info=info)

        window.record_request(count=50)
        assert window.should_wait() is False

    def test_should_wait_true(self):
        info = RateLimitInfo("test", 10, 60, "test")
        window = RateWindow(limit_info=info)

        window.record_request(count=10)
        assert window.should_wait() is True

    def test_wait_time_not_limited(self):
        info = RateLimitInfo("test", 100, 60, "test")
        window = RateWindow(limit_info=info)

        window.record_request(count=5)
        assert window.wait_time() == 0


class TestRateTracker:
    """Tests for RateTracker."""

    def test_init_creates_windows(self):
        tracker = RateTracker()
        assert "mediawiki_auth" in tracker.windows
        assert "ores" in tracker.windows
        assert "pageviews" in tracker.windows

    def test_record_api_calls(self):
        tracker = RateTracker()
        tracker.record("mediawiki_auth", count=5)

        status = tracker.get_status("mediawiki_auth")
        assert status["current"] == 5
        assert status["total_session"] == 5

    def test_get_status_unknown_api(self):
        tracker = RateTracker()
        status = tracker.get_status("nonexistent_api")
        assert "error" in status

    def test_get_all_status(self):
        tracker = RateTracker()
        tracker.record("mediawiki_auth", count=3)
        tracker.record("ores", count=2)

        all_status = tracker.get_all_status()
        assert "mediawiki_auth" in all_status
        assert "ores" in all_status
        assert all_status["mediawiki_auth"]["current"] == 3
        assert all_status["ores"]["current"] == 2

    def test_get_summary(self):
        tracker = RateTracker()
        tracker.record("mediawiki_auth", count=10)

        summary = tracker.get_summary()
        assert "Rate Limit Usage:" in summary
        assert "MediaWiki" in summary

    def test_get_compact_summary_empty(self):
        tracker = RateTracker()
        summary = tracker.get_compact_summary()
        assert summary == "No API usage"

    def test_get_compact_summary_with_usage(self):
        tracker = RateTracker()
        tracker.record("mediawiki_auth", count=5)

        summary = tracker.get_compact_summary()
        assert "MediaWiki" in summary
        assert "5/5000" in summary

    def test_singleton_instance(self):
        # Reset singleton for clean test
        RateTracker._instance = None

        tracker1 = RateTracker.get_instance()
        tracker2 = RateTracker.get_instance()

        assert tracker1 is tracker2

        # Cleanup
        RateTracker._instance = None


class TestSpeedTestResult:
    """Tests for SpeedTestResult."""

    def test_str_success(self):
        result = SpeedTestResult(
            download_mbps=50.5,
            test_size_bytes=10240,
            duration_seconds=0.2,
            success=True,
        )
        assert "50.50 Mbps" in str(result)
        assert "10.0 KB" in str(result)

    def test_str_failure(self):
        result = SpeedTestResult(
            download_mbps=0,
            test_size_bytes=0,
            duration_seconds=0,
            success=False,
            error="Connection timeout",
        )
        assert "failed" in str(result)
        assert "Connection timeout" in str(result)


class TestCheckInternetSpeed:
    """Tests for check_internet_speed function."""

    def test_speed_test_returns_result(self):
        """Test that speed test returns a result (may fail in offline environments)."""
        result = check_internet_speed(timeout=5.0)

        # Should return a SpeedTestResult regardless of success/failure
        assert isinstance(result, SpeedTestResult)

    def test_speed_test_with_invalid_url(self):
        """Test speed test with invalid URL returns failure."""
        result = check_internet_speed(
            test_url="https://invalid.nonexistent.domain.xyz/test",
            timeout=2.0,
        )

        assert result.success is False
        assert result.error is not None


class TestEstimatePullCapacity:
    """Tests for estimate_pull_capacity function."""

    def test_estimate_with_good_speed(self):
        capacity = estimate_pull_capacity(100.0, "mediawiki_auth")

        assert "estimated_cases_per_hour" in capacity
        assert "limiting_factor" in capacity
        assert capacity["speed_mbps"] == 100.0
        assert capacity["estimated_cases_per_hour"] > 0

    def test_estimate_rate_limited(self):
        """With very fast connection, rate limit should be limiting factor."""
        capacity = estimate_pull_capacity(1000.0, "mediawiki_auth")

        assert capacity["limiting_factor"] == "rate_limit"

    def test_estimate_bandwidth_limited(self):
        """With very slow connection, bandwidth should be limiting factor."""
        capacity = estimate_pull_capacity(0.001, "mediawiki_auth")

        assert capacity["limiting_factor"] == "bandwidth"

    def test_estimate_unknown_api(self):
        capacity = estimate_pull_capacity(100.0, "nonexistent_api")

        assert "error" in capacity


class TestKnownRateLimits:
    """Tests for known rate limits configuration."""

    def test_mediawiki_auth_limit(self):
        limit = RATE_LIMITS["mediawiki_auth"]
        assert limit.limit == 5000
        assert limit.window_seconds == 3600

    def test_mediawiki_anon_limit(self):
        limit = RATE_LIMITS["mediawiki_anon"]
        assert limit.limit == 500
        assert limit.window_seconds == 3600

    def test_ores_limit(self):
        limit = RATE_LIMITS["ores"]
        assert limit.limit == 100
        assert limit.window_seconds == 1

    def test_pageviews_limit(self):
        limit = RATE_LIMITS["pageviews"]
        assert limit.limit == 100
        assert limit.window_seconds == 1

    def test_all_limits_have_descriptions(self):
        for name, limit in RATE_LIMITS.items():
            assert limit.description, f"{name} missing description"
