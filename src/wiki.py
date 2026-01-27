"""Wikipedia API client wrapper using Pywikibot."""

from __future__ import annotations

import logging
import time
from functools import wraps
from typing import Callable, TypeVar

import pywikibot
from pywikibot.exceptions import APIError, ServerError

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_on_rate_limit(
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to retry API calls on rate limit or server errors.

    Uses exponential backoff with jitter.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay between retries

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
                            delay = min(base_delay * (2**attempt), max_delay)
                            logger.warning(
                                f"Rate limit hit: {error_code}. "
                                f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})"
                            )
                            time.sleep(delay)
                            continue
                    # Server errors (5xx) - retry with backoff
                    elif isinstance(e, ServerError):
                        if attempt < max_retries:
                            delay = min(base_delay * (2**attempt), max_delay)
                            logger.warning(
                                f"Server error: {e}. "
                                f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})"
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

    def __init__(self, lang: str = "en", project: str = "wikipedia"):
        """
        Initialize Wikipedia client.

        Args:
            lang: Language code (default: "en")
            project: Wikimedia project (default: "wikipedia")
        """
        self.site = pywikibot.Site(lang, project)
        self.lang = lang
        self.project = project

    def get_page(self, title: str) -> pywikibot.Page:
        """Get a Wikipedia page by title."""
        return pywikibot.Page(self.site, title)

    def get_category(self, name: str) -> pywikibot.Category:
        """Get a Wikipedia category by name."""
        return pywikibot.Category(self.site, name)

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
        except Exception:
            pass
        return protection

    def get_talk_page(self, title: str) -> pywikibot.Page | None:
        """Get the talk page for an article."""
        page = self.get_page(title)
        talk = page.toggleTalkPage()
        return talk if talk.exists() else None
