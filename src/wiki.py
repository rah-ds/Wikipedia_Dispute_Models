"""Wikipedia API client wrapper using Pywikibot."""

from __future__ import annotations

import pywikibot
import os
import time


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

    def get_page(self, title: str) -> pywikibot.Page:
        """Get a Wikipedia page by title."""
        return pywikibot.Page(self.site, title)

    def get_category(self, name: str) -> pywikibot.Category:
        """Get a Wikipedia category by name."""
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
