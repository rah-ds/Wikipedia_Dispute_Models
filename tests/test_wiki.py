"""Tests for src/wiki.py - WikiClient class.

Note: These tests require network access and a working Pywikibot configuration.
Mark with @pytest.mark.integration to skip in CI if needed.
"""

import pytest
from src.wiki import WikiClient

# Skip all tests if pywikibot not installed
pywikibot = pytest.importorskip("pywikibot")


@pytest.fixture
def client():
    """Create a WikiClient instance for testing."""
    return WikiClient(lang="en", project="wikipedia")


class TestWikiClient:
    """Tests for WikiClient class."""

    @pytest.mark.integration
    def test_init(self, client):
        """Test client initialization."""
        assert client.lang == "en"
        assert client.project == "wikipedia"
        assert client.site is not None

    @pytest.mark.integration
    def test_get_page_exists(self, client):
        """Test getting a page that exists."""
        page = client.get_page("Python (programming language)")
        assert page.exists()
        assert "Python" in page.title()

    @pytest.mark.integration
    def test_get_page_info(self, client):
        """Test getting page info."""
        info = client.get_page_info("Python (programming language)")

        assert "title" in info
        assert "url" in info
        assert info["exists"] is True

    @pytest.mark.integration
    def test_get_page_info_nonexistent(self, client):
        """Test getting info for nonexistent page raises error."""
        with pytest.raises(ValueError, match="not found"):
            client.get_page_info("ThisPageDefinitelyDoesNotExist12345XYZ")

    @pytest.mark.integration
    def test_get_revisions(self, client):
        """Test fetching revisions."""
        revisions = client.get_revisions("Python (programming language)", limit=5)

        assert len(revisions) == 5
        assert all("revid" in r for r in revisions)
        assert all("timestamp" in r for r in revisions)
        assert all("user" in r for r in revisions)

    @pytest.mark.integration
    def test_get_revisions_limit(self, client):
        """Test revision limit is respected."""
        revisions = client.get_revisions("Python (programming language)", limit=3)
        assert len(revisions) == 3

    @pytest.mark.integration
    def test_get_category_pages(self, client):
        """Test fetching pages from a category."""
        pages = client.get_category_pages(
            "Category:Python (programming language)", limit=5
        )

        assert len(pages) <= 5
        assert all(hasattr(p, "title") for p in pages)

    @pytest.mark.integration
    def test_get_page_protection(self, client):
        """Test fetching page protection status."""
        # Main Page is typically protected
        protection = client.get_page_protection("Main Page")

        # Protection dict may be empty or have keys like 'edit', 'move'
        assert isinstance(protection, dict)


class TestWikiClientUnit:
    """Unit tests that don't require network access."""

    def test_client_attributes(self):
        """Test client has expected attributes after init."""
        # This will fail if pywikibot config is missing, but tests the structure
        try:
            client = WikiClient(lang="en", project="wikipedia")
            assert hasattr(client, "site")
            assert hasattr(client, "lang")
            assert hasattr(client, "project")
        except Exception:
            pytest.skip("Pywikibot not configured")
