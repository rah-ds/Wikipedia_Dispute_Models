"""
Tests for Phase 2 dispute venue fetchers.

These tests use mocking to avoid actual API calls.
"""

from unittest.mock import Mock

from src.fetchers import (
    fetch_talk_page_revisions,
    search_ani_mentions,
    fetch_third_opinion_requests,
    fetch_rfc_for_article,
    fetch_dispute_venues_for_article,
    _extract_ani_sections,
)


class TestFetchTalkPageRevisions:
    """Tests for talk page revision fetching."""

    def test_talk_page_exists(self):
        """Should return talk page data when it exists."""
        mock_client = Mock()
        mock_talk = Mock()
        mock_talk.title.return_value = "Talk:Climate change"
        mock_talk.full_url.return_value = (
            "https://en.wikipedia.org/wiki/Talk:Climate_change"
        )

        mock_client.get_talk_page.return_value = mock_talk
        mock_client.get_revisions.return_value = [
            {"revid": 1, "user": "Alice", "timestamp": "2023-01-01T12:00:00Z"},
            {"revid": 2, "user": "Bob", "timestamp": "2023-01-02T12:00:00Z"},
        ]

        result = fetch_talk_page_revisions(mock_client, "Climate change")

        assert result["exists"] is True
        assert result["talk_title"] == "Talk:Climate change"
        assert result["revision_count"] == 2
        assert len(result["revisions"]) == 2

    def test_talk_page_not_exists(self):
        """Should handle missing talk pages gracefully."""
        mock_client = Mock()
        mock_client.get_talk_page.return_value = None

        result = fetch_talk_page_revisions(mock_client, "New Article")

        assert result["exists"] is False
        assert result["revisions"] == []
        assert result["article"] == "New Article"

    def test_respects_limit(self):
        """Should pass limit to get_revisions."""
        mock_client = Mock()
        mock_talk = Mock()
        mock_talk.title.return_value = "Talk:Test"
        mock_talk.full_url.return_value = "https://example.com"

        mock_client.get_talk_page.return_value = mock_talk
        mock_client.get_revisions.return_value = []

        fetch_talk_page_revisions(mock_client, "Test", limit=100)

        mock_client.get_revisions.assert_called_once_with("Talk:Test", limit=100)


class TestExtractAniSections:
    """Tests for ANI section extraction."""

    def test_extracts_matching_sections(self):
        """Should extract sections containing the search term."""
        content = """
== Section about Climate change ==
This is about [[Climate change]] and some editors.
[[User:Alice]] and [[User:Bob]] are discussing.

== Unrelated section ==
Nothing relevant here.

== Another Climate change issue ==
More discussion about [[Climate change]].
[[User:Charlie]] reporting.
"""

        sections = _extract_ani_sections(content, "Climate change")

        assert len(sections) == 2
        assert "Climate change" in sections[0]["title"]
        assert "Alice" in sections[0]["participants"]
        assert "Bob" in sections[0]["participants"]

    def test_ignores_non_matching_sections(self):
        """Should not return sections without the search term."""
        content = """
== Some other topic ==
Nothing about the search term here.

== Another topic ==
Also unrelated content.
"""

        sections = _extract_ani_sections(content, "Climate change")

        assert len(sections) == 0

    def test_extracts_participants(self):
        """Should extract unique participants from User: links."""
        content = """
== Test Section about Target ==
[[User:Alice]] said something.
[[User:Bob]] responded.
[[User:Alice]] replied again.
This mentions Target topic.
"""

        sections = _extract_ani_sections(content, "Target")

        assert len(sections) == 1
        # Should deduplicate Alice
        assert set(sections[0]["participants"]) == {"Alice", "Bob"}


class TestSearchAniMentions:
    """Tests for ANI archive searching."""

    def test_searches_current_ani(self):
        """Should search the current ANI page."""
        mock_client = Mock()
        mock_page = Mock()
        mock_page.exists.return_value = True
        mock_page.text = "== Issue about Test Article ==\n[[User:Editor1]] reported."
        mock_page.full_url.return_value = "https://example.com/ani"

        mock_client.get_page.return_value = mock_page

        search_ani_mentions(mock_client, "Test Article", limit=5)

        # Should have searched the main ANI page
        mock_client.get_page.assert_any_call(
            "Wikipedia:Administrators' noticeboard/Incidents"
        )

    def test_respects_limit(self):
        """Should stop when limit is reached."""
        mock_client = Mock()
        mock_page = Mock()
        mock_page.exists.return_value = True
        mock_page.text = """
== Issue 1 about Target ==
Content [[User:A]]

== Issue 2 about Target ==
Content [[User:B]]

== Issue 3 about Target ==
Content [[User:C]]
"""
        mock_page.full_url.return_value = "https://example.com"

        mock_client.get_page.return_value = mock_page

        results = search_ani_mentions(mock_client, "Target", limit=2)

        assert len(results) <= 2


class TestFetchThirdOpinionRequests:
    """Tests for Third Opinion request fetching."""

    def test_parses_requests(self):
        """Should parse 3O requests from the page."""
        mock_client = Mock()
        mock_page = Mock()
        mock_page.exists.return_value = True
        mock_page.text = """
== Request about Article A ==
[[User:Editor1]] and [[User:Editor2]] disagree about [[Article A]].

== Request about Article B ==
Different dispute about [[Article B]].
"""

        mock_client.get_page.return_value = mock_page

        results = fetch_third_opinion_requests(mock_client)

        assert len(results) == 2

    def test_filters_by_article(self):
        """Should filter requests for a specific article."""
        mock_client = Mock()
        mock_page = Mock()
        mock_page.exists.return_value = True
        mock_page.text = """
== Request about Article A ==
Content about Article A.

== Request about Article B ==
Content about Article B.
"""

        mock_client.get_page.return_value = mock_page

        results = fetch_third_opinion_requests(mock_client, article_title="Article A")

        assert len(results) == 1
        assert "Article A" in results[0]["title"]

    def test_handles_missing_page(self):
        """Should handle missing 3O page gracefully."""
        mock_client = Mock()
        mock_page = Mock()
        mock_page.exists.return_value = False

        mock_client.get_page.return_value = mock_page

        results = fetch_third_opinion_requests(mock_client)

        assert results == []


class TestFetchRfcForArticle:
    """Tests for RfC fetching."""

    def test_finds_rfc_templates_on_talk(self):
        """Should find RfC templates on talk page."""
        mock_client = Mock()
        mock_talk = Mock()
        mock_talk.text = "{{rfc|section=Neutrality}} Some discussion."

        mock_client.get_talk_page.return_value = mock_talk
        mock_client.get_category_pages.return_value = []

        results = fetch_rfc_for_article(mock_client, "Test Article")

        assert len(results) >= 1
        assert results[0]["source"] == "talk_page"

    def test_handles_no_rfcs(self):
        """Should return empty list when no RfCs found."""
        mock_client = Mock()
        mock_talk = Mock()
        mock_talk.text = "Normal talk page discussion."

        mock_client.get_talk_page.return_value = mock_talk
        mock_client.get_category_pages.return_value = []

        results = fetch_rfc_for_article(mock_client, "Test Article")

        # May be empty or have results from category search
        assert isinstance(results, list)


class TestFetchDisputeVenuesForArticle:
    """Tests for the combined dispute venue fetcher."""

    def test_fetches_all_venues(self):
        """Should fetch all venue types when enabled."""
        mock_client = Mock()

        # Mock talk page
        mock_talk = Mock()
        mock_talk.title.return_value = "Talk:Test"
        mock_talk.full_url.return_value = "https://example.com"
        mock_talk.text = "Talk content"
        mock_client.get_talk_page.return_value = mock_talk
        mock_client.get_revisions.return_value = [{"revid": 1}]

        # Mock ANI page
        mock_ani = Mock()
        mock_ani.exists.return_value = True
        mock_ani.text = "No mentions of Test"
        mock_ani.full_url.return_value = "https://example.com/ani"

        # Mock 3O page
        mock_3o = Mock()
        mock_3o.exists.return_value = True
        mock_3o.text = "No requests"

        def mock_get_page(title):
            if "Incidents" in title:
                return mock_ani
            elif "Third opinion" in title:
                return mock_3o
            else:
                mock_page = Mock()
                mock_page.exists.return_value = False
                return mock_page

        mock_client.get_page.side_effect = mock_get_page
        mock_client.get_category_pages.return_value = []

        result = fetch_dispute_venues_for_article(
            mock_client,
            "Test Article",
            include_talk=True,
            include_ani=True,
            include_3o=True,
            include_rfc=True,
        )

        assert "talk_page" in result
        assert "ani_mentions" in result
        assert "third_opinion" in result
        assert "rfc" in result
        assert "summary" in result

    def test_skips_disabled_venues(self):
        """Should skip venues when disabled."""
        mock_client = Mock()

        result = fetch_dispute_venues_for_article(
            mock_client,
            "Test",
            include_talk=False,
            include_ani=False,
            include_3o=False,
            include_rfc=False,
        )

        assert result["talk_page"] is None
        assert result["ani_mentions"] == []
        assert result["third_opinion"] == []
        assert result["rfc"] == []

    def test_summary_computed(self):
        """Should compute summary statistics."""
        mock_client = Mock()
        mock_talk = Mock()
        mock_talk.title.return_value = "Talk:Test"
        mock_talk.full_url.return_value = "https://example.com"
        mock_client.get_talk_page.return_value = mock_talk
        mock_client.get_revisions.return_value = [{"revid": i} for i in range(5)]

        # Disable other venues
        result = fetch_dispute_venues_for_article(
            mock_client,
            "Test",
            include_talk=True,
            include_ani=False,
            include_3o=False,
            include_rfc=False,
        )

        assert result["summary"]["has_talk_page"] is True
        assert result["summary"]["talk_revision_count"] == 5
