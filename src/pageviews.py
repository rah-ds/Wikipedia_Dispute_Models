"""Wikimedia Pageviews API client.

Fetches page view statistics for Wikipedia articles to understand
article visibility and traffic patterns during disputes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

import requests

logger = logging.getLogger(__name__)

# Pageviews API endpoint
PAGEVIEWS_BASE_URL = "https://wikimedia.org/api/rest_v1/metrics/pageviews"


@dataclass
class PageviewData:
    """Pageview statistics for a page."""

    title: str
    project: str = "en.wikipedia"
    views: list[dict] = field(default_factory=list)
    total_views: int = 0
    avg_daily_views: float = 0.0
    max_daily_views: int = 0
    min_daily_views: int = 0

    def compute_stats(self) -> None:
        """Compute aggregate statistics from views."""
        if not self.views:
            return

        daily_views = [v.get("views", 0) for v in self.views]
        self.total_views = sum(daily_views)
        self.avg_daily_views = self.total_views / len(daily_views)
        self.max_daily_views = max(daily_views)
        self.min_daily_views = min(daily_views)


class PageviewsClient:
    """
    Client for Wikimedia Pageviews API.

    Fetches pageview statistics for articles to understand visibility.
    """

    def __init__(
        self,
        project: str = "en.wikipedia",
        user_agent: str = "WikipediaDisputeModels/1.0",
        rate_limit: float = 100.0,  # Pageviews API allows 100 req/s
    ):
        """
        Initialize Pageviews client.

        Args:
            project: Wikimedia project (e.g., "en.wikipedia", "de.wikipedia")
            user_agent: User agent for API requests
            rate_limit: Max requests per second
        """
        self.project = project
        self.user_agent = user_agent
        self.min_delay = 1.0 / rate_limit
        self._last_request = 0.0

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "application/json",
            }
        )

    def _throttle(self) -> None:
        """Apply rate limiting."""
        elapsed = time.time() - self._last_request
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        self._last_request = time.time()

    def _encode_title(self, title: str) -> str:
        """Encode title for URL (spaces -> underscores, URL encode)."""
        import urllib.parse

        return urllib.parse.quote(title.replace(" ", "_"), safe="")

    def get_article_views(
        self,
        title: str,
        start: str | datetime,
        end: str | datetime,
        granularity: Literal["daily", "monthly"] = "daily",
        access: Literal[
            "all-access", "desktop", "mobile-app", "mobile-web"
        ] = "all-access",
        agent: Literal["all-agents", "user", "spider", "automated"] = "user",
    ) -> PageviewData:
        """
        Fetch pageview counts for an article.

        Args:
            title: Article title
            start: Start date (YYYYMMDD or datetime)
            end: End date (YYYYMMDD or datetime)
            granularity: "daily" or "monthly"
            access: Access method filter
            agent: Agent type filter

        Returns:
            PageviewData with views and statistics
        """
        # Format dates
        if isinstance(start, datetime):
            start = start.strftime("%Y%m%d")
        if isinstance(end, datetime):
            end = end.strftime("%Y%m%d")

        encoded_title = self._encode_title(title)
        url = (
            f"{PAGEVIEWS_BASE_URL}/per-article/{self.project}/{access}/{agent}/"
            f"{encoded_title}/{granularity}/{start}/{end}"
        )

        self._throttle()

        data = PageviewData(title=title, project=self.project)

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            result = response.json()

            data.views = result.get("items", [])
            data.compute_stats()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"No pageview data for {title}")
            else:
                logger.error(f"Pageviews API error for {title}: {e}")
        except Exception as e:
            logger.error(f"Pageviews request failed for {title}: {e}")

        return data

    def get_views_last_n_days(
        self,
        title: str,
        days: int = 30,
    ) -> PageviewData:
        """
        Get pageviews for the last N days.

        Args:
            title: Article title
            days: Number of days to fetch

        Returns:
            PageviewData with views and statistics
        """
        end = datetime.now()
        start = end - timedelta(days=days)
        return self.get_article_views(title, start, end)

    def get_views_around_date(
        self,
        title: str,
        date: str | datetime,
        days_before: int = 7,
        days_after: int = 7,
    ) -> PageviewData:
        """
        Get pageviews around a specific date (e.g., dispute start).

        Args:
            title: Article title
            date: Center date
            days_before: Days before center date
            days_after: Days after center date

        Returns:
            PageviewData with views and statistics
        """
        if isinstance(date, str):
            date = datetime.strptime(date, "%Y-%m-%d")

        start = date - timedelta(days=days_before)
        end = date + timedelta(days=days_after)
        return self.get_article_views(title, start, end)

    def get_traffic_spike(
        self,
        title: str,
        date: str | datetime,
        baseline_days: int = 30,
        event_days: int = 7,
    ) -> dict:
        """
        Detect if there was a traffic spike around a date.

        Args:
            title: Article title
            date: Event date (e.g., dispute filing)
            baseline_days: Days before event for baseline
            event_days: Days after event to measure

        Returns:
            Dictionary with spike analysis
        """
        if isinstance(date, str):
            date = datetime.strptime(date, "%Y-%m-%d")

        # Get baseline traffic
        baseline_end = date - timedelta(days=1)
        baseline_start = baseline_end - timedelta(days=baseline_days)
        baseline_data = self.get_article_views(title, baseline_start, baseline_end)

        # Get event traffic
        event_start = date
        event_end = date + timedelta(days=event_days)
        event_data = self.get_article_views(title, event_start, event_end)

        # Calculate spike
        baseline_avg = baseline_data.avg_daily_views or 1
        event_avg = event_data.avg_daily_views or 0
        spike_ratio = event_avg / baseline_avg if baseline_avg > 0 else 0

        return {
            "title": title,
            "date": date.isoformat(),
            "baseline_avg_views": baseline_avg,
            "event_avg_views": event_avg,
            "spike_ratio": spike_ratio,
            "had_spike": spike_ratio > 2.0,  # 2x baseline = spike
            "event_max_views": event_data.max_daily_views,
        }

    def get_top_articles(
        self,
        date: str | datetime,
        access: Literal[
            "all-access", "desktop", "mobile-app", "mobile-web"
        ] = "all-access",
        limit: int = 100,
    ) -> list[dict]:
        """
        Get top viewed articles for a specific date.

        Args:
            date: Date to query (YYYYMMDD or datetime)
            access: Access method filter
            limit: Number of articles to return

        Returns:
            List of top articles with view counts
        """
        if isinstance(date, datetime):
            year = date.strftime("%Y")
            month = date.strftime("%m")
            day = date.strftime("%d")
        else:
            year = date[:4]
            month = date[4:6]
            day = date[6:8]

        url = f"{PAGEVIEWS_BASE_URL}/top/{self.project}/{access}/{year}/{month}/{day}"

        self._throttle()

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            result = response.json()

            items = result.get("items", [])
            if items:
                articles = items[0].get("articles", [])
                return articles[:limit]

        except Exception as e:
            logger.error(f"Failed to fetch top articles: {e}")

        return []


def get_article_traffic(
    title: str,
    days: int = 30,
    project: str = "en.wikipedia",
) -> dict:
    """
    Convenience function to get article traffic summary.

    Args:
        title: Article title
        days: Number of days to analyze
        project: Wikimedia project

    Returns:
        Dictionary with traffic metrics
    """
    client = PageviewsClient(project=project)
    data = client.get_views_last_n_days(title, days)

    return {
        "title": title,
        "total_views": data.total_views,
        "avg_daily_views": round(data.avg_daily_views, 2),
        "max_daily_views": data.max_daily_views,
        "min_daily_views": data.min_daily_views,
        "days_analyzed": len(data.views),
    }
