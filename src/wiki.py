"""Wikipedia API client wrapper using Pywikibot."""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime
from functools import wraps
from typing import Callable, TypeVar

import pywikibot
from pywikibot import data as pywikibot_data
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

    def _api_request(self, **params) -> dict:
        """
        Make a direct API request using pywikibot's Request class.

        This is the proper way to make API requests that works across
        different pywikibot versions.

        Args:
            **params: API parameters

        Returns:
            API response as dictionary
        """
        request = pywikibot_data.api.Request(site=self.site, parameters=params)
        return request.submit()

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
            resp = self._api_request(**params)
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
        return results

    @retry_on_rate_limit()
    def get_revisions(
        self,
        title: str,
        limit: int | None = None,
        content: bool = False,
        include_tags: bool = True,
    ) -> list[dict]:
        """
        Fetch revision history for a page.

        Args:
            title: Page title
            limit: Maximum revisions to fetch (None = all)
            content: Whether to include page content
            include_tags: Whether to include edit tags (mw-revert, mw-undo, etc.)

        Returns:
            List of revision dictionaries with optional tags
        """
        page = self.get_page(title)
        if not page.exists():
            raise ValueError(f"Page not found: {title}")

        revisions = []
        for i, rev in enumerate(page.revisions(content=content)):
            if limit and i >= limit:
                break
            rev_data = {
                "revid": rev.revid,
                "parentid": getattr(rev, "parentid", None),
                "timestamp": str(rev.timestamp),
                "user": rev.user,
                "comment": rev.comment or "",
                "size": getattr(rev, "size", None),
            }
            if include_tags:
                rev_data["tags"] = getattr(rev, "tags", [])
            revisions.append(rev_data)
        return revisions

    @retry_on_rate_limit()
    def get_revisions_with_tags(
        self,
        title: str,
        limit: int | None = 500,
    ) -> list[dict]:
        """
        Fetch revision history with edit tags using direct API call.

        This method uses the API directly to ensure tags are included,
        which is more reliable than pywikibot for tag retrieval.

        Args:
            title: Page title
            limit: Maximum revisions to fetch (default: 500)

        Returns:
            List of revision dictionaries with tags
        """
        self._track_request()
        revisions = []
        continue_token = None

        while True:
            params = {
                "action": "query",
                "prop": "revisions",
                "titles": title,
                "rvprop": "ids|timestamp|user|comment|size|tags",
                "rvlimit": min(limit or 500, 500),
                "format": "json",
            }
            if continue_token:
                params["rvcontinue"] = continue_token

            try:
                response = self._api_request(**params)
            except Exception as e:
                logger.error(f"Failed to fetch revisions for {title}: {e}")
                raise

            pages = response.get("query", {}).get("pages", {})
            for page_id, page_data in pages.items():
                if page_id == "-1":
                    raise ValueError(f"Page not found: {title}")
                for rev in page_data.get("revisions", []):
                    revisions.append(
                        {
                            "revid": rev.get("revid"),
                            "parentid": rev.get("parentid"),
                            "timestamp": rev.get("timestamp"),
                            "user": rev.get("user"),
                            "comment": rev.get("comment", ""),
                            "size": rev.get("size"),
                            "tags": rev.get("tags", []),
                        }
                    )

            # Check if we have enough or need to continue
            if limit and len(revisions) >= limit:
                revisions = revisions[:limit]
                break

            continue_data = response.get("continue")
            if continue_data and "rvcontinue" in continue_data:
                continue_token = continue_data["rvcontinue"]
            else:
                break

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

    # =========================================================================
    # User Information Methods
    # =========================================================================

    @retry_on_rate_limit()
    def get_user_info(self, username: str) -> dict | None:
        """
        Fetch user information including groups, registration, and edit count.

        Args:
            username: Wikipedia username

        Returns:
            Dictionary with user metadata or None if user doesn't exist
        """
        self._track_request()
        params = {
            "action": "query",
            "list": "users",
            "ususers": username,
            "usprop": "groups|editcount|registration|blockinfo|gender",
            "format": "json",
        }

        try:
            response = self._api_request(**params)
        except Exception as e:
            logger.error(f"Failed to fetch user info for {username}: {e}")
            raise

        users = response.get("query", {}).get("users", [])
        if not users:
            return None

        user = users[0]
        if "missing" in user or "invalid" in user:
            return None

        return {
            "username": user.get("name"),
            "user_id": user.get("userid"),
            "edit_count": user.get("editcount", 0),
            "registration": user.get("registration"),
            "groups": user.get("groups", []),
            "is_admin": "sysop" in user.get("groups", []),
            "is_bot": "bot" in user.get("groups", []),
            "gender": user.get("gender"),
            # Block info if currently blocked
            "is_blocked": "blockid" in user,
            "block_reason": user.get("blockreason"),
            "blocked_by": user.get("blockedby"),
            "block_expiry": user.get("blockexpiry"),
        }

    @retry_on_rate_limit()
    def get_users_info(
        self,
        usernames: list[str],
        batch_size: int = 50,
    ) -> dict[str, dict]:
        """
        Fetch information for multiple users in batches.

        Args:
            usernames: List of Wikipedia usernames
            batch_size: Number of users per request (max 50)

        Returns:
            Dictionary mapping username to user info
        """
        results = {}

        for i in range(0, len(usernames), batch_size):
            batch = usernames[i : i + batch_size]
            self._track_request()

            params = {
                "action": "query",
                "list": "users",
                "ususers": "|".join(batch),
                "usprop": "groups|editcount|registration|blockinfo|gender",
                "format": "json",
            }

            try:
                response = self._api_request(**params)
            except Exception as e:
                logger.error(f"Failed to fetch users info: {e}")
                continue

            for user in response.get("query", {}).get("users", []):
                if "missing" in user or "invalid" in user:
                    continue
                username = user.get("name")
                results[username] = {
                    "username": username,
                    "user_id": user.get("userid"),
                    "edit_count": user.get("editcount", 0),
                    "registration": user.get("registration"),
                    "groups": user.get("groups", []),
                    "is_admin": "sysop" in user.get("groups", []),
                    "is_bot": "bot" in user.get("groups", []),
                    "gender": user.get("gender"),
                    "is_blocked": "blockid" in user,
                    "block_reason": user.get("blockreason"),
                    "blocked_by": user.get("blockedby"),
                    "block_expiry": user.get("blockexpiry"),
                }

        return results

    # =========================================================================
    # Block History Methods
    # =========================================================================

    @retry_on_rate_limit()
    def get_user_blocks(
        self,
        username: str,
        limit: int | None = 100,
    ) -> list[dict]:
        """
        Fetch block history for a user.

        Args:
            username: Wikipedia username
            limit: Maximum blocks to fetch (None = all)

        Returns:
            List of block events (newest first)
        """
        self._track_request()
        blocks = []
        continue_token = None

        while True:
            params = {
                "action": "query",
                "list": "blocks",
                "bkusers": username,
                "bkprop": "id|user|by|timestamp|expiry|reason|flags",
                "bklimit": min(limit or 500, 500),
                "format": "json",
            }
            if continue_token:
                params["bkcontinue"] = continue_token

            try:
                response = self._api_request(**params)
            except Exception as e:
                logger.error(f"Failed to fetch blocks for {username}: {e}")
                raise

            for block in response.get("query", {}).get("blocks", []):
                blocks.append(
                    {
                        "block_id": block.get("id"),
                        "user": block.get("user"),
                        "blocked_by": block.get("by"),
                        "timestamp": block.get("timestamp"),
                        "expiry": block.get("expiry"),
                        "reason": block.get("reason", ""),
                        "is_autoblock": block.get("autoblock", False),
                        "allows_email": not block.get("noemail", False),
                        "allows_usertalk": not block.get("nousertalk", False),
                        "is_partial": block.get("partial", False),
                    }
                )

            # Check if we have enough or need to continue
            if limit and len(blocks) >= limit:
                blocks = blocks[:limit]
                break

            continue_data = response.get("continue")
            if continue_data and "bkcontinue" in continue_data:
                continue_token = continue_data["bkcontinue"]
            else:
                break

        return blocks

    @retry_on_rate_limit()
    def get_block_log(
        self,
        username: str,
        limit: int | None = 100,
    ) -> list[dict]:
        """
        Fetch block/unblock log entries for a user.

        This provides more detail than get_user_blocks, including
        unblock events and block modifications.

        Args:
            username: Wikipedia username
            limit: Maximum entries to fetch

        Returns:
            List of log events (newest first)
        """
        self._track_request()
        entries = []
        continue_token = None

        while True:
            params = {
                "action": "query",
                "list": "logevents",
                "letype": "block",
                "letitle": f"User:{username}",
                "leprop": "ids|title|type|user|timestamp|comment|details",
                "lelimit": min(limit or 500, 500),
                "format": "json",
            }
            if continue_token:
                params["lecontinue"] = continue_token

            try:
                response = self._api_request(**params)
            except Exception as e:
                logger.error(f"Failed to fetch block log for {username}: {e}")
                raise

            for entry in response.get("query", {}).get("logevents", []):
                entries.append(
                    {
                        "log_id": entry.get("logid"),
                        "action": entry.get("action"),  # block, unblock, reblock
                        "target_user": username,
                        "admin": entry.get("user"),
                        "timestamp": entry.get("timestamp"),
                        "comment": entry.get("comment", ""),
                        "duration": entry.get("params", {}).get("duration"),
                        "expiry": entry.get("params", {}).get("expiry"),
                        "flags": entry.get("params", {}).get("flags", []),
                    }
                )

            # Check if we have enough or need to continue
            if limit and len(entries) >= limit:
                entries = entries[:limit]
                break

            continue_data = response.get("continue")
            if continue_data and "lecontinue" in continue_data:
                continue_token = continue_data["lecontinue"]
            else:
                break

        return entries

    # =========================================================================
    # Log Events Methods
    # =========================================================================

    @retry_on_rate_limit()
    def get_log_events(
        self,
        log_type: str,
        title: str | None = None,
        user: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Fetch log events filtered by type, page, or user.

        Args:
            log_type: Log type (block, protect, rights, delete, move, etc.)
            title: Filter by page title (optional)
            user: Filter by acting user (optional)
            limit: Maximum entries to fetch

        Returns:
            List of log events
        """
        self._track_request()
        entries = []
        continue_token = None

        while len(entries) < limit:
            params = {
                "action": "query",
                "list": "logevents",
                "letype": log_type,
                "leprop": "ids|title|type|user|timestamp|comment|details",
                "lelimit": min(limit - len(entries), 500),
                "format": "json",
            }
            if title:
                params["letitle"] = title
            if user:
                params["leuser"] = user
            if continue_token:
                params["lecontinue"] = continue_token

            try:
                response = self._api_request(**params)
            except Exception as e:
                logger.error(f"Failed to fetch {log_type} log: {e}")
                raise

            for entry in response.get("query", {}).get("logevents", []):
                entries.append(
                    {
                        "log_id": entry.get("logid"),
                        "log_type": entry.get("type"),
                        "action": entry.get("action"),
                        "title": entry.get("title"),
                        "user": entry.get("user"),
                        "timestamp": entry.get("timestamp"),
                        "comment": entry.get("comment", ""),
                        "params": entry.get("params", {}),
                    }
                )

            continue_data = response.get("continue")
            if continue_data and "lecontinue" in continue_data:
                continue_token = continue_data["lecontinue"]
            else:
                break

        return entries[:limit]

    @retry_on_rate_limit()
    def get_protection_log(self, title: str, limit: int = 50) -> list[dict]:
        """
        Get protection history for a page.

        Args:
            title: Page title
            limit: Maximum entries to fetch

        Returns:
            List of protection events
        """
        events = self.get_log_events("protect", title=title, limit=limit)

        # Enhance with parsed protection details
        for event in events:
            params = event.get("params", {})
            event["protection_level"] = params.get("description", "")
            event["cascade"] = params.get("cascade", False)

        return events

    # =========================================================================
    # Article Quality Methods
    # =========================================================================

    # =========================================================================
    # Revision Diff Methods
    # =========================================================================

    @retry_on_rate_limit()
    def compare_revisions(
        self,
        from_rev: int,
        to_rev: int,
    ) -> dict:
        """
        Get diff between two revisions.

        Args:
            from_rev: Source revision ID
            to_rev: Target revision ID

        Returns:
            Dictionary with diff information
        """
        self._track_request()
        params = {
            "action": "compare",
            "fromrev": from_rev,
            "torev": to_rev,
            "prop": "diff|size|comment|user|title",
            "format": "json",
        }

        try:
            response = self._api_request(**params)
        except Exception as e:
            logger.error(f"Failed to compare revisions {from_rev} -> {to_rev}: {e}")
            raise

        compare = response.get("compare", {})
        return {
            "from_revid": compare.get("fromrevid"),
            "to_revid": compare.get("torevid"),
            "from_title": compare.get("fromtitle"),
            "to_title": compare.get("totitle"),
            "from_user": compare.get("fromuser"),
            "to_user": compare.get("touser"),
            "from_comment": compare.get("fromcomment", ""),
            "to_comment": compare.get("tocomment", ""),
            "from_size": compare.get("fromsize"),
            "to_size": compare.get("tosize"),
            "diff_html": compare.get("*", ""),
            "size_diff": (compare.get("tosize", 0) or 0)
            - (compare.get("fromsize", 0) or 0),
        }

    @retry_on_rate_limit()
    def get_revision_content(self, revid: int) -> dict | None:
        """
        Get content of a specific revision.

        Args:
            revid: Revision ID

        Returns:
            Dictionary with revision content or None
        """
        self._track_request()
        params = {
            "action": "query",
            "prop": "revisions",
            "revids": revid,
            "rvprop": "ids|timestamp|user|comment|content|size|tags",
            "rvslots": "main",
            "format": "json",
        }

        try:
            response = self._api_request(**params)
        except Exception as e:
            logger.error(f"Failed to get revision {revid}: {e}")
            raise

        pages = response.get("query", {}).get("pages", {})
        for page_id, page_data in pages.items():
            if page_id == "-1":
                return None
            revs = page_data.get("revisions", [])
            if revs:
                rev = revs[0]
                content = rev.get("slots", {}).get("main", {}).get("*", "")
                return {
                    "revid": rev.get("revid"),
                    "parentid": rev.get("parentid"),
                    "timestamp": rev.get("timestamp"),
                    "user": rev.get("user"),
                    "comment": rev.get("comment", ""),
                    "size": rev.get("size"),
                    "tags": rev.get("tags", []),
                    "content": content,
                }
        return None

    @retry_on_rate_limit()
    def get_page_assessments(self, title: str) -> dict:
        """
        Get WikiProject quality and importance ratings for a page.

        Args:
            title: Page title

        Returns:
            Dictionary with assessment data
        """
        self._track_request()
        params = {
            "action": "query",
            "titles": title,
            "prop": "pageassessments",
            "palimit": "max",
            "format": "json",
        }

        try:
            response = self._api_request(**params)
        except Exception as e:
            logger.error(f"Failed to fetch assessments for {title}: {e}")
            raise

        pages = response.get("query", {}).get("pages", {})
        for page_id, page_data in pages.items():
            if page_id == "-1":
                return {"title": title, "assessments": {}}

            assessments = page_data.get("pageassessments", {})

            # Find highest quality and importance
            quality_order = ["FA", "GA", "B", "C", "Start", "Stub"]
            importance_order = ["Top", "High", "Mid", "Low"]

            highest_quality = None
            highest_importance = None

            for project, rating in assessments.items():
                quality = rating.get("class", "")
                importance = rating.get("importance", "")

                if quality in quality_order:
                    if highest_quality is None or quality_order.index(
                        quality
                    ) < quality_order.index(highest_quality):
                        highest_quality = quality

                if importance in importance_order:
                    if highest_importance is None or importance_order.index(
                        importance
                    ) < importance_order.index(highest_importance):
                        highest_importance = importance

            return {
                "title": title,
                "assessments": assessments,
                "highest_quality": highest_quality,
                "highest_importance": highest_importance,
            }

        return {"title": title, "assessments": {}}

    # =========================================================================
    # Abuse Filter Methods
    # =========================================================================

    @retry_on_rate_limit()
    def get_abuse_log(
        self,
        user: str | None = None,
        title: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Fetch abuse filter log entries.

        Args:
            user: Filter by username (optional)
            title: Filter by page title (optional)
            limit: Maximum entries to fetch

        Returns:
            List of abuse filter log entries
        """
        self._track_request()
        entries = []
        continue_token = None

        while len(entries) < limit:
            params = {
                "action": "query",
                "list": "abuselog",
                "aflprop": "ids|filter|user|title|action|result|timestamp|details",
                "afllimit": min(limit - len(entries), 500),
                "format": "json",
            }
            if user:
                params["afluser"] = user
            if title:
                params["afltitle"] = title
            if continue_token:
                params["aflstart"] = continue_token

            try:
                response = self._api_request(**params)
            except Exception as e:
                logger.error(f"Failed to fetch abuse log: {e}")
                raise

            for entry in response.get("query", {}).get("abuselog", []):
                entries.append(
                    {
                        "log_id": entry.get("id"),
                        "filter_id": entry.get("filter_id"),
                        "filter_name": entry.get("filter"),
                        "user": entry.get("user"),
                        "title": entry.get("title"),
                        "action": entry.get("action"),
                        "result": entry.get("result"),
                        "timestamp": entry.get("timestamp"),
                        "revid": entry.get("revid"),
                    }
                )

            continue_data = response.get("continue")
            if continue_data and "aflstart" in continue_data:
                continue_token = continue_data["aflstart"]
            else:
                break

        return entries[:limit]

    @retry_on_rate_limit()
    def get_user_abuse_hits(self, username: str, limit: int = 50) -> dict:
        """
        Get summary of abuse filter hits for a user.

        Args:
            username: Wikipedia username
            limit: Maximum entries to check

        Returns:
            Dictionary with abuse filter statistics
        """
        entries = self.get_abuse_log(user=username, limit=limit)

        # Group by filter
        by_filter: dict[str, int] = {}
        by_action: dict[str, int] = {}
        by_result: dict[str, int] = {}

        for entry in entries:
            filter_name = entry.get("filter_name", "unknown")
            action = entry.get("action", "unknown")
            result = entry.get("result", "unknown")

            by_filter[filter_name] = by_filter.get(filter_name, 0) + 1
            by_action[action] = by_action.get(action, 0) + 1
            by_result[result] = by_result.get(result, 0) + 1

        return {
            "username": username,
            "total_hits": len(entries),
            "by_filter": by_filter,
            "by_action": by_action,
            "by_result": by_result,
            "entries": entries,
        }
