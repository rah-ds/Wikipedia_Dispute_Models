"""Rate limit tracking and internet speed monitoring.

This module provides utilities for:
- Tracking API request counts against known rate limits
- Measuring internet connection speed
- Estimating remaining capacity and time to limit reset
"""

from __future__ import annotations

import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar


@dataclass
class RateLimitInfo:
    """Information about a rate limit."""

    name: str
    limit: int
    window_seconds: int
    description: str = ""

    @property
    def window_display(self) -> str:
        """Human-readable window duration."""
        if self.window_seconds >= 3600:
            return f"{self.window_seconds // 3600}h"
        elif self.window_seconds >= 60:
            return f"{self.window_seconds // 60}m"
        return f"{self.window_seconds}s"


# Known API rate limits
RATE_LIMITS: dict[str, RateLimitInfo] = {
    "mediawiki_anon": RateLimitInfo(
        name="MediaWiki API (anonymous)",
        limit=500,
        window_seconds=3600,
        description="Unauthenticated requests to en.wikipedia.org/w/api.php",
    ),
    "mediawiki_auth": RateLimitInfo(
        name="MediaWiki API (authenticated)",
        limit=5000,
        window_seconds=3600,
        description="Authenticated requests with bot password or OAuth",
    ),
    "ores": RateLimitInfo(
        name="ORES/Lift Wing API",
        limit=100,
        window_seconds=1,
        description="ML scoring requests (batches of 50 revisions)",
    ),
    "pageviews": RateLimitInfo(
        name="Pageviews API",
        limit=100,
        window_seconds=1,
        description="Page traffic statistics",
    ),
    "xtools": RateLimitInfo(
        name="XTools API",
        limit=50,
        window_seconds=60,
        description="Pre-aggregated user statistics (estimate)",
    ),
}


@dataclass
class RateWindow:
    """Tracks requests within a sliding window."""

    limit_info: RateLimitInfo
    requests: list[float] = field(default_factory=list)
    total_requests: int = 0

    def record_request(self, count: int = 1) -> None:
        """Record request(s) at current time."""
        now = time.time()
        for _ in range(count):
            self.requests.append(now)
        self.total_requests += count
        self._cleanup()

    def _cleanup(self) -> None:
        """Remove requests outside the window."""
        cutoff = time.time() - self.limit_info.window_seconds
        self.requests = [t for t in self.requests if t > cutoff]

    @property
    def current_count(self) -> int:
        """Requests in current window."""
        self._cleanup()
        return len(self.requests)

    @property
    def remaining(self) -> int:
        """Remaining requests in current window."""
        return max(0, self.limit_info.limit - self.current_count)

    @property
    def usage_pct(self) -> float:
        """Percentage of limit used."""
        return (self.current_count / self.limit_info.limit) * 100

    @property
    def time_to_reset(self) -> float:
        """Seconds until oldest request falls out of window."""
        if not self.requests:
            return 0
        oldest = min(self.requests)
        return max(0, oldest + self.limit_info.window_seconds - time.time())

    def should_wait(self) -> bool:
        """Check if we should wait before next request."""
        return self.remaining <= 0

    def wait_time(self) -> float:
        """Recommended wait time if rate limited."""
        if not self.should_wait():
            return 0
        return self.time_to_reset + 0.1  # Small buffer


@dataclass
class RateTracker:
    """Tracks multiple rate limits across API calls."""

    windows: dict[str, RateWindow] = field(default_factory=dict)
    start_time: datetime = field(default_factory=datetime.now)

    # Class-level singleton for global tracking
    _instance: ClassVar[RateTracker | None] = None

    @classmethod
    def get_instance(cls) -> RateTracker:
        """Get global rate tracker instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __post_init__(self) -> None:
        """Initialize windows for all known limits."""
        for key, limit_info in RATE_LIMITS.items():
            if key not in self.windows:
                self.windows[key] = RateWindow(limit_info=limit_info)

    def record(self, api_name: str, count: int = 1) -> None:
        """Record API request(s)."""
        if api_name in self.windows:
            self.windows[api_name].record_request(count)

    def get_status(self, api_name: str) -> dict:
        """Get status for a specific API."""
        if api_name not in self.windows:
            return {"error": f"Unknown API: {api_name}"}

        window = self.windows[api_name]
        return {
            "name": window.limit_info.name,
            "current": window.current_count,
            "limit": window.limit_info.limit,
            "remaining": window.remaining,
            "usage_pct": window.usage_pct,
            "window": window.limit_info.window_display,
            "total_session": window.total_requests,
            "should_wait": window.should_wait(),
            "wait_time": window.wait_time(),
        }

    def get_all_status(self) -> dict[str, dict]:
        """Get status for all tracked APIs."""
        return {name: self.get_status(name) for name in self.windows}

    def get_summary(self) -> str:
        """Get formatted summary of rate usage."""
        lines = ["Rate Limit Usage:"]
        for name, window in self.windows.items():
            if window.total_requests > 0:
                status = "⚠️ LIMIT" if window.should_wait() else "✓"
                lines.append(
                    f"  {window.limit_info.name}: "
                    f"{window.current_count}/{window.limit_info.limit} "
                    f"({window.usage_pct:.1f}%) [{status}] "
                    f"(session total: {window.total_requests})"
                )
        if len(lines) == 1:
            lines.append("  No API calls recorded yet")
        return "\n".join(lines)

    def get_compact_summary(self) -> str:
        """Get single-line summary for progress bars."""
        active = [
            f"{w.limit_info.name.split()[0]}:{w.current_count}/{w.limit_info.limit}"
            for w in self.windows.values()
            if w.total_requests > 0
        ]
        return " | ".join(active) if active else "No API usage"


@dataclass
class SpeedTestResult:
    """Result of internet speed test."""

    download_mbps: float
    test_size_bytes: int
    duration_seconds: float
    timestamp: datetime = field(default_factory=datetime.now)
    success: bool = True
    error: str | None = None

    def __str__(self) -> str:
        if not self.success:
            return f"Speed test failed: {self.error}"
        return (
            f"Download: {self.download_mbps:.2f} Mbps "
            f"({self.test_size_bytes / 1024:.1f} KB in {self.duration_seconds:.2f}s)"
        )


def check_internet_speed(
    test_url: str = "https://www.wikipedia.org/portal/wikipedia.org/assets/img/Wikipedia-logo-v2.png",
    timeout: float = 10.0,
) -> SpeedTestResult:
    """
    Check internet speed by downloading a small file.

    Uses Wikipedia's logo as a test file to avoid external dependencies.
    This provides a rough estimate suitable for logging purposes.

    Args:
        test_url: URL to download for speed test
        timeout: Request timeout in seconds

    Returns:
        SpeedTestResult with download speed in Mbps
    """
    try:
        start = time.time()

        request = urllib.request.Request(
            test_url,
            headers={"User-Agent": "WikiDisputeModels/1.0 (speed test)"},
        )

        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()

        duration = time.time() - start
        size_bytes = len(data)

        # Calculate speed in Mbps (megabits per second)
        speed_mbps = (size_bytes * 8) / (duration * 1_000_000)

        return SpeedTestResult(
            download_mbps=speed_mbps,
            test_size_bytes=size_bytes,
            duration_seconds=duration,
        )

    except Exception as e:
        return SpeedTestResult(
            download_mbps=0,
            test_size_bytes=0,
            duration_seconds=0,
            success=False,
            error=str(e),
        )


def estimate_pull_capacity(
    speed_mbps: float,
    api_key: str = "mediawiki_auth",
) -> dict:
    """
    Estimate pull capacity based on speed and rate limits.

    Args:
        speed_mbps: Current download speed in Mbps
        api_key: Which API rate limit to use for estimation

    Returns:
        Dictionary with capacity estimates
    """
    limit_info = RATE_LIMITS.get(api_key)
    if not limit_info:
        return {"error": f"Unknown API: {api_key}"}

    # Estimate: average API response ~10KB, average case needs ~50 API calls
    avg_response_kb = 10
    avg_calls_per_case = 50

    # Calculate throughput constraints
    # Rate limit constraint
    max_calls_per_hour = limit_info.limit
    cases_per_hour_rate = max_calls_per_hour / avg_calls_per_case

    # Bandwidth constraint (if very slow connection)
    kb_per_second = (speed_mbps * 1000) / 8
    max_kb_per_hour = kb_per_second * 3600
    cases_per_hour_bandwidth = max_kb_per_hour / (avg_response_kb * avg_calls_per_case)

    # Actual limit is the lower of the two
    cases_per_hour = min(cases_per_hour_rate, cases_per_hour_bandwidth)
    limiting_factor = (
        "rate_limit" if cases_per_hour_rate < cases_per_hour_bandwidth else "bandwidth"
    )

    return {
        "speed_mbps": speed_mbps,
        "rate_limit": f"{limit_info.limit}/{limit_info.window_display}",
        "estimated_cases_per_hour": round(cases_per_hour, 1),
        "limiting_factor": limiting_factor,
        "assumptions": {
            "avg_response_kb": avg_response_kb,
            "avg_calls_per_case": avg_calls_per_case,
        },
    }
