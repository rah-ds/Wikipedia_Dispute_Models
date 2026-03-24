"""Wikipedia API client wrapper using Pywikibot."""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime
from functools import wraps
from typing import Callable, TypeVar

import pywikibot
from pywikibot.exceptions import APIError, ServerError
import os

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_on_rate_limit(
    max_retries: int = 10,
    base_delay: float = 2.0,
    max_delay: float = 300.0,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to retry API calls on rate limit or server errors.

    Uses exponential backoff with jitter for all-day running.

    Args:
        max_retries: Maximum number of retry attempts (default: 10)
        base_delay: Initial delay in seconds (default: 2.0)
        max_delay: Maximum delay between retries (default: 300s = 5 min)

    Returns:
        Decorated function with retry logic
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (APIError, ServerError) as e:
                    last_exception = e
                    error_code = getattr(e, "code", str(e))

                    # Check if it's a rate limit error
                    if (
                        "ratelimit" in str(error_code).lower()
                        or "maxlag" in str(error_code).lower()
                    ):
                        if attempt < max_retries:
                            # Exponential backoff with jitter
                            delay = min(base_delay * (2**attempt), max_delay)
                            jitter = random.uniform(0.5, 1.5)
                            delay *= jitter
                            logger.warning(
                                f"Rate limit hit: {error_code}. "
                                f"Waiting {delay:.1f}s (attempt {attempt + 1}/{max_retries})"
                            )
                            time.sleep(delay)
                            continue
                    # Server errors (5xx) - retry with backoff
                    elif isinstance(e, ServerError):
                        if attempt < max_retries:
                            delay = min(base_delay * (2**attempt), max_delay)
                            jitter = random.uniform(0.5, 1.5)
                            delay *= jitter
                            logger.warning(
                                f"Server error: {e}. "
                                f"Waiting {delay:.1f}s (attempt {attempt + 1}/{max_retries})"
                            )
                            time.sleep(delay)
                            continue
                    # Non-retryable error
                    raise
                except Exception:
                    # Unexpected errors - don't retry
                    raise

            # All retries exhausted
            logger.error(f"Max retries ({max_retries}) exceeded for {func.__name__}")
            if last_exception is not None:
                raise last_exception
            raise RuntimeError(
                f"Max retries ({max_retries}) exceeded for {func.__name__}"
            )

        return wrapper

    return decorator


class WikiClient:
    """Client for interacting with Wikipedia via Pywikibot."""

    def __init__(
        self, lang: str = "en", project: str = "wikipedia", use_oauth: bool = True
    ):
        """
        Initialize Wikipedia client.

        Args:
            lang: Language code (default: "en")
            project: Wikimedia project (default: "wikipedia")
        """
        self.site = pywikibot.Site(lang, project)
        self.lang = lang
        self.project = project

        if use_oauth:
            token = os.getenv("WIKIPEDIA_ACCESS_TOKEN")
            if not token:
                raise ValueError(
                    "WIKIPEDIA_ACCESS_TOKEN not found in environment variables"
                )

            # Setup OAuth headers
            self.site._loginstatus = (
                True  # pretend logged in to bypass anonymous checks
            )
            self.site._custom_headers = {"Authorization": f"Bearer {token}"}

        # Request tracking
        self._request_count = 0
        self._hourly_counts: dict[str, int] = {}  # hour -> count
        self._start_time = datetime.now()

    def _track_request(self) -> None:
        """Track API request and log hourly stats."""
        self._request_count += 1
        hour_key = datetime.now().strftime("%Y-%m-%d %H:00")
        self._hourly_counts[hour_key] = self._hourly_counts.get(hour_key, 0) + 1

        # Log every 50 requests
        if self._request_count % 50 == 0:
            current_hour = self._hourly_counts.get(hour_key, 0)
            logger.info(
                f"API requests: {self._request_count} total, "
                f"{current_hour} this hour ({hour_key})"
            )

    def get_stats(self) -> dict:
        """Get request statistics."""
        return {
            "total_requests": self._request_count,
            "hourly_counts": self._hourly_counts.copy(),
            "start_time": self._start_time.isoformat(),
            "runtime_minutes": (datetime.now() - self._start_time).total_seconds() / 60,
        }

    def log_stats(self) -> None:
        """Log current request statistics."""
        stats = self.get_stats()
        logger.info("=== API Request Stats ===")
        logger.info(f"Total requests: {stats['total_requests']}")
        logger.info(f"Runtime: {stats['runtime_minutes']:.1f} minutes")
        for hour, count in sorted(stats["hourly_counts"].items()):
            logger.info(f"  {hour}: {count} requests")

    def get_page(self, title: str) -> pywikibot.Page:
        """Get a Wikipedia page by title."""
        self._track_request()
        return pywikibot.Page(self.site, title)

    def get_category(self, name: str) -> pywikibot.Category:
        """Get a Wikipedia category by name."""
        self._track_request()
        return pywikibot.Category(self.site, name)

    def get_pages_latest(
        self, titles: list[str], batch_size: int = 50, sleep_time: float = 1.0
    ) -> list[dict]:
        """
        Fetch the latest revision for multiple pages in batches with throttle.

        Args:
            titles: List of page titles
            batch_size: Number of pages to fetch per request
            sleep_time: Seconds to sleep between batches

        Returns:
            List of dicts with latest revision info per page
        """
        results = []

        for i in range(0, len(titles), batch_size):
            batch = titles[i : i + batch_size]
            params = {
                "action": "query",
                "prop": "revisions",
                "rvprop": "ids|timestamp|user|comment|content",
                "titles": "|".join(batch),
                "format": "json",
            }
            resp = self.site._client._simple_request(**params).submit()
            for page_id, page in resp["query"]["pages"].items():
                rev = page["revisions"][0]
                results.append(
                    {
                        "title": page["title"],
                        "page_id": page_id,
                        "user": rev["user"],
                        "timestamp": rev["timestamp"],
                        "comment": rev.get("comment", ""),
                        "text": rev["*"],
                    }
                )
            # Throttle between batches
            time.sleep(sleep_time)
        return results

    @retry_on_rate_limit()
    def get_revisions(
        self,
        title: str,
        limit: int | None = None,
        content: bool = False,
    ) -> list[dict]:
        """
        Fetch revision history for a page.

        Args:
            title: Page title
            limit: Maximum revisions to fetch (None = all)
            content: Whether to include page content

        Returns:
            List of revision dictionaries
        """
        page = self.get_page(title)
        if not page.exists():
            raise ValueError(f"Page not found: {title}")

        revisions = []
        for i, rev in enumerate(page.revisions(content=content)):
            if limit and i >= limit:
                break
            revisions.append(
                {
                    "revid": rev.revid,
                    "parentid": getattr(rev, "parentid", None),
                    "timestamp": str(rev.timestamp),
                    "user": rev.user,
                    "comment": rev.comment or "",
                    "size": getattr(rev, "size", None),
                }
            )
        return revisions

    def get_latest_revision(self, title):
        page = pywikibot.Page(self.site, title)

        text = page.get()  # SAFE for large pages
        latest = page.latest_revision

        return {
            "revid": latest.revid,
            "timestamp": latest.timestamp.isoformat(),
            "user": latest.user,
            "text": text,
        }

    @retry_on_rate_limit()
    def get_page_info(self, title: str) -> dict:
        """
        Get basic page information.

        Args:
            title: Page title

        Returns:
            Dictionary with page metadata
        """
        page = self.get_page(title)
        if not page.exists():
            raise ValueError(f"Page not found: {title}")

        return {
            "title": page.title(),
            "url": page.full_url(),
            "exists": page.exists(),
            "is_redirect": page.isRedirectPage(),
        }

    @retry_on_rate_limit()
    def get_category_pages(
        self,
        category_name: str,
        limit: int | None = None,
    ) -> list[pywikibot.Page]:
        """
        Get pages in a category.

        Args:
            category_name: Category name (with or without "Category:" prefix)
            limit: Maximum pages to return

        Returns:
            List of Page objects
        """
        if not category_name.startswith("Category:"):
            category_name = f"Category:{category_name}"

        cat = self.get_category(category_name)
        pages = []
        for i, page in enumerate(cat.articles()):
            if limit and i >= limit:
                break
            pages.append(page)
        return pages

    def get_page_protection(self, title: str) -> dict:
        """Get page protection status."""
        page = self.get_page(title)
        protection = {}
        try:
            for prot in page.protection():
                protection[prot[0]] = {
                    "level": prot[1],
                    "expiry": str(prot[2]) if len(prot) > 2 else None,
                }
        except Exception as e:
            logger.warning(f"Failed to get protection status for '{title}': {e}")
        return protection

    def get_talk_page(self, title: str) -> pywikibot.Page | None:
        """Get the talk page for an article."""
        page = self.get_page(title)
        talk = page.toggleTalkPage()
        return talk if talk.exists() else None
