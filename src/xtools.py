"""XTools API client for pre-aggregated user statistics.

XTools provides pre-computed statistics about Wikipedia users,
avoiding the need to compute them from raw edit data.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)

# XTools API endpoint
XTOOLS_BASE_URL = "https://xtools.wmcloud.org/api"


@dataclass
class UserStats:
    """Pre-aggregated user statistics from XTools."""

    username: str
    project: str = "en.wikipedia.org"

    # Edit statistics
    total_edit_count: int = 0
    live_edit_count: int = 0
    deleted_edit_count: int = 0

    # By namespace
    edits_by_namespace: dict[str, int] = field(default_factory=dict)

    # Time-based
    first_edit: str | None = None
    last_edit: str | None = None
    days_active: int = 0

    # Quality metrics
    pages_created: int = 0
    pages_created_live: int = 0
    pages_created_deleted: int = 0

    # Behavioral
    thank_count: int = 0
    reverted_count: int = 0
    reverts_done: int = 0

    # User status
    user_groups: list[str] = field(default_factory=list)
    is_admin: bool = False
    is_bot: bool = False
    registration: str | None = None

    # Error handling
    error: str | None = None


class XToolsClient:
    """
    Client for XTools API.

    XTools provides pre-aggregated statistics about Wikipedia users
    and articles, avoiding expensive computations.
    """

    def __init__(
        self,
        project: str = "en.wikipedia.org",
        user_agent: str = "WikipediaDisputeModels/1.0",
        rate_limit: float = 5.0,  # Conservative rate limit
    ):
        """
        Initialize XTools client.

        Args:
            project: Wikimedia project domain
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

    def _encode_username(self, username: str) -> str:
        """Encode username for URL."""
        import urllib.parse

        return urllib.parse.quote(username.replace(" ", "_"), safe="")

    def get_user_stats(self, username: str) -> UserStats:
        """
        Fetch aggregated statistics for a user.

        Args:
            username: Wikipedia username

        Returns:
            UserStats with pre-computed metrics
        """
        encoded_name = self._encode_username(username)
        url = f"{XTOOLS_BASE_URL}/user/simple_editcount/{self.project}/{encoded_name}"

        self._throttle()

        stats = UserStats(username=username, project=self.project)

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            stats.total_edit_count = data.get("live_edit_count", 0) + data.get(
                "deleted_edit_count", 0
            )
            stats.live_edit_count = data.get("live_edit_count", 0)
            stats.deleted_edit_count = data.get("deleted_edit_count", 0)
            stats.user_groups = data.get("user_groups", [])
            stats.is_admin = "sysop" in stats.user_groups
            stats.is_bot = "bot" in stats.user_groups

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                stats.error = f"User {username} not found"
            else:
                stats.error = str(e)
            logger.warning(f"XTools error for {username}: {e}")
        except Exception as e:
            stats.error = str(e)
            logger.error(f"XTools request failed for {username}: {e}")

        return stats

    def get_user_edit_counts_by_namespace(self, username: str) -> dict[str, int]:
        """
        Get edit counts broken down by namespace.

        Args:
            username: Wikipedia username

        Returns:
            Dictionary mapping namespace name to edit count
        """
        encoded_name = self._encode_username(username)
        url = f"{XTOOLS_BASE_URL}/user/namespace_totals/{self.project}/{encoded_name}"

        self._throttle()

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Extract namespace counts
            counts = {}
            for ns_data in data.get("namespace_totals", []):
                ns_name = ns_data.get("namespace", "")
                count = ns_data.get("count", 0)
                counts[ns_name] = count

            return counts

        except Exception as e:
            logger.error(f"Failed to get namespace totals for {username}: {e}")
            return {}

    def get_pages_created(
        self,
        username: str,
        limit: int = 100,
    ) -> list[dict]:
        """
        Get pages created by a user.

        Args:
            username: Wikipedia username
            limit: Maximum pages to return

        Returns:
            List of page creation records
        """
        encoded_name = self._encode_username(username)
        url = f"{XTOOLS_BASE_URL}/user/pages/{self.project}/{encoded_name}"

        self._throttle()

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            pages = data.get("pages", [])
            return pages[:limit]

        except Exception as e:
            logger.error(f"Failed to get pages created by {username}: {e}")
            return []

    def get_top_edited_pages(
        self,
        username: str,
        limit: int = 20,
    ) -> list[dict]:
        """
        Get pages most edited by a user.

        Args:
            username: Wikipedia username
            limit: Maximum pages to return

        Returns:
            List of pages with edit counts
        """
        encoded_name = self._encode_username(username)
        url = f"{XTOOLS_BASE_URL}/user/top_edits/{self.project}/{encoded_name}"

        self._throttle()

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            pages = data.get("top_edits", [])
            return pages[:limit]

        except Exception as e:
            logger.error(f"Failed to get top edited pages for {username}: {e}")
            return []

    def get_month_counts(self, username: str) -> list[dict]:
        """
        Get monthly edit counts for a user.

        Args:
            username: Wikipedia username

        Returns:
            List of monthly counts [{month: YYYY-MM, count: N}, ...]
        """
        encoded_name = self._encode_username(username)
        url = f"{XTOOLS_BASE_URL}/user/month_counts/{self.project}/{encoded_name}"

        self._throttle()

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            return data.get("month_counts", [])

        except Exception as e:
            logger.error(f"Failed to get month counts for {username}: {e}")
            return []

    def get_article_info(self, title: str) -> dict:
        """
        Get aggregated statistics for an article.

        Args:
            title: Article title

        Returns:
            Dictionary with article statistics
        """
        import urllib.parse

        encoded_title = urllib.parse.quote(title.replace(" ", "_"), safe="")
        url = f"{XTOOLS_BASE_URL}/page/articleinfo/{self.project}/{encoded_title}"

        self._throttle()

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Failed to get article info for {title}: {e}")
            return {}

    def get_article_top_editors(
        self,
        title: str,
        limit: int = 20,
    ) -> list[dict]:
        """
        Get top editors for an article.

        Args:
            title: Article title
            limit: Maximum editors to return

        Returns:
            List of top editors with edit counts
        """
        import urllib.parse

        encoded_title = urllib.parse.quote(title.replace(" ", "_"), safe="")
        url = f"{XTOOLS_BASE_URL}/page/top_editors/{self.project}/{encoded_title}"

        self._throttle()

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            editors = data.get("top_editors", [])
            return editors[:limit]

        except Exception as e:
            logger.error(f"Failed to get top editors for {title}: {e}")
            return []


def get_user_summary(username: str, project: str = "en.wikipedia.org") -> dict:
    """
    Convenience function to get user summary statistics.

    Args:
        username: Wikipedia username
        project: Wikimedia project

    Returns:
        Dictionary with user statistics
    """
    client = XToolsClient(project=project)
    stats = client.get_user_stats(username)

    if stats.error:
        return {"username": username, "error": stats.error}

    return {
        "username": username,
        "total_edits": stats.total_edit_count,
        "live_edits": stats.live_edit_count,
        "deleted_edits": stats.deleted_edit_count,
        "is_admin": stats.is_admin,
        "is_bot": stats.is_bot,
        "user_groups": stats.user_groups,
    }
