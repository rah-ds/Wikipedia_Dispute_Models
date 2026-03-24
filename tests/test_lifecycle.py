"""Tests for src/lifecycle.py."""

from unittest.mock import MagicMock

from src.lifecycle import (
    extract_article_links,
    extract_participants,
    get_arb_case_prefix,
    find_arb_case_path,
    search_drn_mentions,
    ARB_PATH_PATTERNS,
    ARB_SUBPAGES,
)


class TestExtractArticleLinks:
    """Tests for extract_article_links function."""

    def test_extracts_basic_wikilinks(self):
        content = "This is about [[Climate change]] and [[Global warming]]."
        links = extract_article_links(content)
        assert "Climate change" in links
        assert "Global warming" in links

    def test_filters_user_namespace(self):
        content = "[[User:Example]] edited [[Article name]]."
        links = extract_article_links(content)
        assert "Article name" in links
        assert "Example" not in links
        assert "User:Example" not in links

    def test_filters_talk_namespace(self):
        content = "See [[Talk:Article]] and [[Article]]."
        links = extract_article_links(content)
        assert "Article" in links
        assert "Talk:Article" not in links

    def test_filters_wikipedia_namespace(self):
        content = "See [[Wikipedia:Policies]] and [[Real article]]."
        links = extract_article_links(content)
        assert "Real article" in links
        assert "Wikipedia:Policies" not in links

    def test_filters_template_namespace(self):
        content = "Uses [[Template:Infobox]] on [[Example page]]."
        links = extract_article_links(content)
        assert "Example page" in links
        assert "Template:Infobox" not in links

    def test_filters_category_namespace(self):
        content = "[[Category:Science]] [[Science]]"
        links = extract_article_links(content)
        assert "Science" in links
        assert "Category:Science" not in links

    def test_handles_section_links(self):
        content = "See [[Article#Section]] for details."
        links = extract_article_links(content)
        assert "Article" in links
        assert "Article#Section" not in links

    def test_skips_anchor_only_links(self):
        content = "See [[#Section]] for more."
        links = extract_article_links(content)
        assert len(links) == 0

    def test_empty_content(self):
        assert extract_article_links("") == []

    def test_no_wikilinks(self):
        content = "Plain text with no links."
        assert extract_article_links(content) == []

    def test_deduplicates_links(self):
        content = "[[Article]] mentioned twice [[Article]]."
        links = extract_article_links(content)
        assert links.count("Article") == 1

    def test_filters_file_namespace(self):
        content = "[[File:Example.jpg]] [[Image:Test.png]] [[Article]]"
        links = extract_article_links(content)
        assert "Article" in links
        assert len(links) == 1

    def test_filters_special_namespace(self):
        content = "[[Special:Contributions/User]] [[Article]]"
        links = extract_article_links(content)
        assert "Article" in links
        assert len(links) == 1


class TestExtractParticipants:
    """Tests for extract_participants function."""

    def test_extracts_user_links(self):
        content = "[[User:Alice]] and [[User:Bob]] discussed this."
        participants = extract_participants(content)
        assert "Alice" in participants
        assert "Bob" in participants

    def test_extracts_user_talk_links(self):
        content = "Posted on [[User talk:Charlie]]."
        participants = extract_participants(content)
        assert "Charlie" in participants

    def test_case_insensitive(self):
        content = "[[user:Dave]] and [[USER:Eve]]"
        participants = extract_participants(content)
        assert "Dave" in participants
        assert "Eve" in participants

    def test_deduplicates_users(self):
        content = "[[User:Alice]] said... [[User talk:Alice]] replied."
        participants = extract_participants(content)
        assert participants.count("Alice") == 1

    def test_empty_content(self):
        assert extract_participants("") == []

    def test_no_user_links(self):
        content = "[[Article]] with no users."
        assert extract_participants(content) == []

    def test_filters_subpage_links(self):
        content = "[[User:/subpage]] should be ignored."
        participants = extract_participants(content)
        assert len(participants) == 0

    def test_filters_anchor_links(self):
        content = "[[User:#section]] should be ignored."
        participants = extract_participants(content)
        assert len(participants) == 0

    def test_handles_piped_links(self):
        content = "[[User:LongUsername|Short]] discussed."
        participants = extract_participants(content)
        assert "LongUsername" in participants


class TestGetArbCasePrefix:
    """Tests for get_arb_case_prefix function."""

    def test_adds_prefix_to_simple_name(self):
        result = get_arb_case_prefix("Climate change")
        assert result == "Wikipedia:Arbitration/Requests/Case/Climate change"

    def test_preserves_full_path(self):
        full_path = "Wikipedia:Arbitration/Requests/Case/Test"
        result = get_arb_case_prefix(full_path)
        assert result == full_path

    def test_preserves_old_format_path(self):
        old_path = "Wikipedia:Arbitration/Old case"
        result = get_arb_case_prefix(old_path)
        assert result == old_path


class TestFindArbCasePath:
    """Tests for find_arb_case_path function."""

    def test_returns_provided_path_if_exists(self):
        mock_client = MagicMock()
        mock_page = MagicMock()
        mock_page.exists.return_value = True
        mock_client.get_page.return_value = mock_page

        prefix, pattern = find_arb_case_path(
            mock_client, "Wikipedia:Arbitration/Requests/Case/Test"
        )

        assert prefix == "Wikipedia:Arbitration/Requests/Case/Test"
        assert pattern == "provided"

    def test_returns_none_if_provided_path_not_found(self):
        mock_client = MagicMock()
        mock_page = MagicMock()
        mock_page.exists.return_value = False
        mock_client.get_page.return_value = mock_page

        prefix, pattern = find_arb_case_path(mock_client, "Wikipedia:Nonexistent/Case")

        assert prefix is None
        assert pattern == "not_found"

    def test_tries_multiple_patterns(self):
        mock_client = MagicMock()

        # First pattern fails, second succeeds
        def mock_get_page(title):
            page = MagicMock()
            if "Requests for arbitration" in title:
                page.exists.return_value = True
            else:
                page.exists.return_value = False
            return page

        mock_client.get_page.side_effect = mock_get_page

        prefix, pattern = find_arb_case_path(mock_client, "Old case")

        assert prefix == "Wikipedia:Requests for arbitration/Old case"
        assert pattern == "Wikipedia:Requests for arbitration/{name}"

    def test_returns_not_found_if_all_patterns_fail(self):
        mock_client = MagicMock()
        mock_page = MagicMock()
        mock_page.exists.return_value = False
        mock_client.get_page.return_value = mock_page

        prefix, pattern = find_arb_case_path(mock_client, "Nonexistent case")

        assert prefix is None
        assert pattern == "not_found"

    def test_handles_exception_in_pattern_check(self):
        mock_client = MagicMock()
        mock_client.get_page.side_effect = Exception("API error")

        prefix, pattern = find_arb_case_path(mock_client, "Test case")

        assert prefix is None
        assert pattern == "not_found"


class TestSearchDrnMentions:
    """Tests for search_drn_mentions function."""

    def test_searches_current_drn_page(self):
        mock_client = MagicMock()
        mock_page = MagicMock()
        mock_page.exists.return_value = True
        mock_page.text = "Discussion about Climate change case"
        mock_page.full_url.return_value = "https://en.wikipedia.org/wiki/WP:DRN"
        mock_client.get_page.return_value = mock_page

        results = search_drn_mentions(mock_client, ["Climate change"], archive_limit=0)

        assert len(results) == 1
        assert results[0]["type"] == "current_drn"
        assert results[0]["search_term"] == "Climate change"
        assert results[0]["found"] is True

    def test_case_insensitive_search(self):
        mock_client = MagicMock()
        mock_page = MagicMock()
        mock_page.exists.return_value = True
        mock_page.text = "CLIMATE CHANGE discussion"
        mock_page.full_url.return_value = "https://example.com"
        mock_client.get_page.return_value = mock_page

        results = search_drn_mentions(mock_client, ["climate change"], archive_limit=0)

        assert len(results) == 1

    def test_no_match_returns_empty(self):
        mock_client = MagicMock()
        mock_page = MagicMock()
        mock_page.exists.return_value = True
        mock_page.text = "Unrelated content"
        mock_client.get_page.return_value = mock_page

        results = search_drn_mentions(mock_client, ["Climate change"], archive_limit=0)

        assert len(results) == 0

    def test_handles_missing_drn_page(self):
        mock_client = MagicMock()
        mock_page = MagicMock()
        mock_page.exists.return_value = False
        mock_client.get_page.return_value = mock_page

        results = search_drn_mentions(mock_client, ["Test"], archive_limit=0)

        assert len(results) == 0

    def test_handles_exception(self):
        mock_client = MagicMock()
        mock_client.get_page.side_effect = Exception("API error")

        results = search_drn_mentions(mock_client, ["Test"], archive_limit=0)

        assert len(results) == 0

    def test_searches_multiple_terms(self):
        mock_client = MagicMock()
        mock_page = MagicMock()
        mock_page.exists.return_value = True
        mock_page.text = "Alice and Bob dispute"
        mock_page.full_url.return_value = "https://example.com"
        mock_client.get_page.return_value = mock_page

        results = search_drn_mentions(
            mock_client, ["Alice", "Bob", "Charlie"], archive_limit=0
        )

        # Alice and Bob found, Charlie not
        assert len(results) == 2
        terms_found = {r["search_term"] for r in results}
        assert terms_found == {"Alice", "Bob"}

    def test_stops_after_consecutive_missing_archives(self):
        mock_client = MagicMock()
        call_count = 0

        def mock_get_page(title):
            nonlocal call_count
            call_count += 1
            page = MagicMock()
            # Current DRN exists, but all archives are missing
            if title == "Wikipedia:Dispute resolution noticeboard":
                page.exists.return_value = True
                page.text = "no matches here"
            else:
                page.exists.return_value = False
            return page

        mock_client.get_page.side_effect = mock_get_page

        search_drn_mentions(mock_client, ["Test"], archive_limit=50)

        # Should stop after 3 consecutive missing archives
        # 1 (current DRN) + 3*2 (archive patterns) = 7 max calls
        assert call_count <= 10


class TestConstants:
    """Tests for module constants."""

    def test_arb_subpages_includes_main(self):
        assert "" in ARB_SUBPAGES

    def test_arb_subpages_includes_decision_pages(self):
        assert "/Proposed decision" in ARB_SUBPAGES
        assert "/Final decision" in ARB_SUBPAGES

    def test_arb_path_patterns_not_empty(self):
        assert len(ARB_PATH_PATTERNS) > 0

    def test_arb_path_patterns_contain_placeholder(self):
        for pattern in ARB_PATH_PATTERNS:
            assert "{name}" in pattern
