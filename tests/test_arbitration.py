"""Tests for enhanced arbitration case fetching."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add src to path for direct import
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arbitration import (
    find_case_path,
    extract_participants,
    extract_article_links,
    search_drn_mentions,
    fetch_full_arbitration_case,
    _is_ip_address,
    _is_valid_username,
    _is_valid_article_title,
    ARB_SUBPAGES,
    ARB_PATH_PATTERNS,
)


class TestExtractParticipants:
    """Tests for participant extraction from wikitext."""

    def test_extract_user_links(self):
        content = "This edit by [[User:Example]] was disputed by [[User:Another]]."
        participants = extract_participants(content)

        assert "Example" in participants
        assert "Another" in participants

    def test_extract_user_talk_links(self):
        content = "See [[User talk:TestUser]] for discussion."
        participants = extract_participants(content)

        assert "TestUser" in participants

    def test_skip_fragments(self):
        content = "[[User:#top]] [[User:/sandbox]]"
        participants = extract_participants(content)

        assert len(participants) == 0

    def test_deduplicate_participants(self):
        content = "[[User:Same]] and [[User:Same]] again [[User talk:Same]]"
        participants = extract_participants(content)

        assert len(participants) == 1
        assert "Same" in participants

    def test_empty_content(self):
        participants = extract_participants("")
        assert len(participants) == 0

    def test_no_users_in_content(self):
        content = "This is just regular text with no user links."
        participants = extract_participants(content)

        assert len(participants) == 0

    def test_skip_ip_addresses(self):
        """IP addresses should be filtered out since user info can't be fetched for them."""
        content = "[[User:166.205.138.68]] [[User:67.233.18.28]] [[User:ValidUser]]"
        participants = extract_participants(content)

        assert "ValidUser" in participants
        assert "166.205.138.68" not in participants
        assert "67.233.18.28" not in participants
        assert len(participants) == 1

    def test_skip_anchors(self):
        """Fragment anchors like User#top should be filtered out."""
        content = "[[User:AGK#top]] [[User:ValidUser]]"
        participants = extract_participants(content)

        assert "ValidUser" in participants
        assert "AGK#top" not in participants
        assert "AGK" not in participants  # Shouldn't extract partial
        assert len(participants) == 1

    def test_skip_subpages(self):
        """User subpages like User/sandbox should be filtered out."""
        content = "[[User:ArtifexMayhem/ArbAbort2011]] [[User:NormalUser]]"
        participants = extract_participants(content)

        assert "NormalUser" in participants
        assert "ArtifexMayhem/ArbAbort2011" not in participants
        assert len(participants) == 1

    def test_mixed_valid_and_invalid(self):
        """Test extraction with a mix of valid users, IPs, anchors, and subpages."""
        content = """
        Discussion between [[User:Editor1]], [[User:Editor2]].
        IP edits from [[User:192.168.1.1]] and [[User:10.0.0.1]].
        See also [[User:Admin#section]] and [[User:Archiver/2020]].
        [[User talk:Editor1]] agreed.
        """
        participants = extract_participants(content)

        assert "Editor1" in participants
        assert "Editor2" in participants
        assert len(participants) == 2

    def test_skip_magic_words(self):
        """Magic words like {{REVISIONUSER}} should be filtered out."""
        content = "[[User:{{REVISIONUSER}}]] [[User:ValidUser]]"
        participants = extract_participants(content)

        assert "ValidUser" in participants
        assert "{{REVISIONUSER}}" not in participants
        assert len(participants) == 1

    def test_skip_long_text(self):
        """Long text strings (likely extraction errors) should be filtered out."""
        long_text = "A" * 150  # More than 100 chars
        content = f"[[User:{long_text}]] [[User:ValidUser]]"
        participants = extract_participants(content)

        assert "ValidUser" in participants
        assert long_text not in participants
        assert len(participants) == 1


class TestIsValidUsername:
    """Tests for username validation."""

    def test_valid_usernames(self):
        assert _is_valid_username("Editor1") is True
        assert _is_valid_username("Some_User_Name") is True
        assert _is_valid_username("Admin") is True

    def test_rejects_magic_words(self):
        assert _is_valid_username("{{REVISIONUSER}}") is False
        assert _is_valid_username("{{PAGENAME}}") is False
        assert _is_valid_username("User{{test}}") is False

    def test_rejects_long_strings(self):
        long_text = "A" * 150
        assert _is_valid_username(long_text) is False

    def test_rejects_newlines(self):
        assert _is_valid_username("User\nName") is False
        assert _is_valid_username("User\rName") is False

    def test_rejects_brackets(self):
        assert _is_valid_username("User[[link]]Name") is False
        assert _is_valid_username("User{braces}Name") is False

    def test_rejects_ip_addresses(self):
        assert _is_valid_username("192.168.1.1") is False
        assert _is_valid_username("10.0.0.1") is False


class TestIsValidArticleTitle:
    """Tests for article title validation."""

    def test_valid_titles(self):
        assert _is_valid_article_title("Climate change") is True
        assert _is_valid_article_title("Global warming") is True
        assert _is_valid_article_title("United States") is True

    def test_rejects_relative_paths(self):
        assert _is_valid_article_title("../Workshop") is False
        assert _is_valid_article_title("../Evidence") is False
        assert _is_valid_article_title("./Subpage") is False

    def test_rejects_interwiki_prefixes(self):
        assert _is_valid_article_title("m:Main Page") is False
        assert _is_valid_article_title("meta:Help") is False
        assert _is_valid_article_title("wikt:word") is False
        assert _is_valid_article_title("wiktionary:definition") is False
        assert _is_valid_article_title("wmuk:Main_Page") is False
        assert _is_valid_article_title("mail:Clerks-l") is False
        assert _is_valid_article_title("foundation:Resolution") is False

    def test_rejects_leading_colons(self):
        assert _is_valid_article_title(":Image:Photo.jpg") is False
        assert _is_valid_article_title(":m:Privacy policy") is False
        assert _is_valid_article_title(":foundation:Resolution") is False

    def test_rejects_magic_words(self):
        assert _is_valid_article_title("{{TALKPAGENAME}}") is False
        assert _is_valid_article_title("{{PAGENAME}}") is False
        assert _is_valid_article_title("Some{{template}}Page") is False

    def test_rejects_urls(self):
        assert _is_valid_article_title("http://example.com") is False
        assert _is_valid_article_title("https://example.com") is False

    def test_rejects_long_titles(self):
        long_title = "A" * 250
        assert _is_valid_article_title(long_title) is False


class TestIsIpAddress:
    """Tests for IP address detection."""

    def test_ipv4_address(self):
        assert _is_ip_address("192.168.1.1") is True
        assert _is_ip_address("166.205.138.68") is True
        assert _is_ip_address("10.0.0.1") is True

    def test_ipv4_edge_cases(self):
        assert _is_ip_address("0.0.0.0") is True
        assert _is_ip_address("255.255.255.255") is True

    def test_ipv6_address(self):
        assert _is_ip_address("2001:0db8:85a3:0000:0000:8a2e:0370:7334") is True
        assert _is_ip_address("::1") is True

    def test_regular_usernames(self):
        assert _is_ip_address("Editor1") is False
        assert _is_ip_address("AGK") is False
        assert _is_ip_address("Some_User_Name") is False

    def test_partial_ip_like_strings(self):
        assert _is_ip_address("192.168") is False
        assert _is_ip_address("192.168.1") is False
        assert _is_ip_address("1.2.3.4.5") is False


class TestExtractArticleLinks:
    """Tests for article link extraction from wikitext."""

    def test_extract_article_links(self):
        content = "See [[Climate change]] and [[Global warming]]."
        articles = extract_article_links(content)

        assert "Climate change" in articles
        assert "Global warming" in articles

    def test_skip_namespace_prefixes(self):
        content = """
        [[User:Example]]
        [[Wikipedia:Policy]]
        [[Talk:Article]]
        [[Template:Example]]
        [[Category:Test]]
        [[File:Image.jpg]]
        [[Article name]]
        """
        articles = extract_article_links(content)

        # Only "Article name" should be extracted
        assert "Article name" in articles
        assert len(articles) == 1

    def test_handle_fragments(self):
        content = "[[Article#Section]] and [[Another article]]"
        articles = extract_article_links(content)

        assert "Article" in articles
        assert "Another article" in articles

    def test_empty_content(self):
        articles = extract_article_links("")
        assert len(articles) == 0

    def test_skip_relative_paths(self):
        """Relative paths like ../Workshop should be filtered out."""
        content = "[[../Workshop]] [[../Evidence]] [[Valid Article]]"
        articles = extract_article_links(content)

        assert "Valid Article" in articles
        assert "../Workshop" not in articles
        assert "../Evidence" not in articles

    def test_skip_interwiki_links(self):
        """Interwiki links like m:, wikt:, etc. should be filtered out."""
        content = """
        [[m:Main Page]]
        [[meta:Help]]
        [[wikt:word]]
        [[wiktionary:definition]]
        [[wmuk:Main_Page]]
        [[Valid Article]]
        """
        articles = extract_article_links(content)

        assert "Valid Article" in articles
        assert len(articles) == 1

    def test_skip_leading_colons(self):
        """Leading colon links should be filtered out."""
        content = "[[:Image:Photo.jpg]] [[:m:Privacy policy]] [[Valid Article]]"
        articles = extract_article_links(content)

        assert "Valid Article" in articles
        # Interwiki and file links with leading colon should be filtered
        assert ":Image:Photo.jpg" not in articles
        assert ":m:Privacy policy" not in articles

    def test_skip_magic_words(self):
        """Magic words/templates should be filtered out."""
        content = "[[{{TALKPAGENAME}}]] [[{{PAGENAME}}]] [[Valid Article]]"
        articles = extract_article_links(content)

        assert "Valid Article" in articles
        assert "{{TALKPAGENAME}}" not in articles
        assert "{{PAGENAME}}" not in articles


class TestFindCasePath:
    """Tests for case path resolution."""

    def test_full_path_provided(self):
        mock_client = MagicMock()
        mock_page = MagicMock()
        mock_page.exists.return_value = True
        mock_client.get_page.return_value = mock_page

        prefix, pattern = find_case_path(
            mock_client, "Wikipedia:Arbitration/Requests/Case/Test"
        )

        assert prefix == "Wikipedia:Arbitration/Requests/Case/Test"
        assert pattern == "provided"

    def test_short_name_modern_format(self):
        mock_client = MagicMock()
        mock_page = MagicMock()
        mock_page.exists.return_value = True
        mock_client.get_page.return_value = mock_page

        prefix, pattern = find_case_path(mock_client, "Test Case")

        assert "Test Case" in prefix
        assert pattern in ARB_PATH_PATTERNS

    def test_case_not_found(self):
        mock_client = MagicMock()
        mock_page = MagicMock()
        mock_page.exists.return_value = False
        mock_client.get_page.return_value = mock_page

        prefix, pattern = find_case_path(mock_client, "Nonexistent")

        assert prefix is None
        assert pattern == "not_found"


class TestArbSubpages:
    """Tests for arbitration subpage constants."""

    def test_subpages_defined(self):
        assert "main" in ARB_SUBPAGES
        assert "evidence" in ARB_SUBPAGES
        assert "workshop" in ARB_SUBPAGES
        assert "proposed_decision" in ARB_SUBPAGES
        assert "remedies" in ARB_SUBPAGES

    def test_main_is_empty_suffix(self):
        assert ARB_SUBPAGES["main"] == ""

    def test_evidence_suffix(self):
        assert ARB_SUBPAGES["evidence"] == "/Evidence"


class TestSearchDrnMentions:
    """Tests for DRN mention searching."""

    def test_finds_mentions_in_current_drn(self):
        mock_client = MagicMock()
        mock_page = MagicMock()
        mock_page.exists.return_value = True
        mock_page.text = "This mentions Climate change dispute"
        mock_page.full_url.return_value = "https://en.wikipedia.org/wiki/WP:DRN"
        mock_client.get_page.return_value = mock_page

        with patch("arbitration.time.sleep"):
            results = search_drn_mentions(
                mock_client, ["Climate change"], archive_limit=1
            )

        assert len(results) >= 1
        assert any(r["type"] == "current_drn" for r in results)

    def test_no_mentions_returns_empty(self):
        mock_client = MagicMock()
        mock_page = MagicMock()
        mock_page.exists.return_value = True
        mock_page.text = "No relevant content here"
        mock_page.full_url.return_value = "https://en.wikipedia.org/wiki/WP:DRN"
        mock_client.get_page.return_value = mock_page

        with patch("arbitration.time.sleep"):
            results = search_drn_mentions(
                mock_client, ["Nonexistent topic"], archive_limit=1
            )

        # May have archive results, but not matching our search term
        matching = [r for r in results if r.get("found")]
        assert len(matching) == 0


class TestFetchFullArbitrationCase:
    """Tests for full arbitration case fetching."""

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()

        # Mock page that exists
        page = MagicMock()
        page.exists.return_value = True
        page.title.return_value = "Wikipedia:Arbitration/Requests/Case/Test"
        page.full_url.return_value = "https://en.wikipedia.org/wiki/Test"
        page.text = """
        This case involves [[User:Editor1]] and [[User:Editor2]].
        Articles: [[Climate change]] and [[Global warming]].
        """

        client.get_page.return_value = page
        client.get_revisions.return_value = [
            {"revid": 1, "timestamp": "2024-01-01T00:00:00Z", "user": "Editor1"}
        ]
        client.get_users_info.return_value = {
            "Editor1": {"edit_count": 1000, "registration": "2020-01-01"}
        }
        client.get_user_blocks.return_value = []
        client.get_user_abuse_hits.return_value = {"total_hits": 0}
        client.get_page_assessments.return_value = {
            "highest_quality": "B",
            "highest_importance": "High",
            "assessments": {},
        }
        client.get_page_protection.return_value = {}
        client.get_protection_log.return_value = []
        client.get_revisions_with_tags.return_value = []

        return client

    def test_returns_expected_structure(self, mock_client):
        with patch("arbitration.search_ani_mentions", return_value=[]):
            with patch("arbitration.time.sleep"):
                result = fetch_full_arbitration_case(
                    mock_client,
                    "Test",
                    enrich_participants=False,
                    enrich_articles=False,
                    include_ani=False,
                    include_drn=False,
                )

        # Check structure
        assert "case_name" in result
        assert "pages" in result
        assert "participants" in result
        assert "articles" in result
        assert "outcome" in result
        assert "summary" in result

    def test_extracts_participants(self, mock_client):
        with patch("arbitration.search_ani_mentions", return_value=[]):
            with patch("arbitration.time.sleep"):
                result = fetch_full_arbitration_case(
                    mock_client,
                    "Test",
                    enrich_participants=False,
                    enrich_articles=False,
                    include_ani=False,
                    include_drn=False,
                )

        assert "Editor1" in result["all_participants"]
        assert "Editor2" in result["all_participants"]

    def test_extracts_articles(self, mock_client):
        with patch("arbitration.search_ani_mentions", return_value=[]):
            with patch("arbitration.time.sleep"):
                result = fetch_full_arbitration_case(
                    mock_client,
                    "Test",
                    enrich_participants=False,
                    enrich_articles=False,
                    include_ani=False,
                    include_drn=False,
                )

        assert "Climate change" in result["all_articles"]
        assert "Global warming" in result["all_articles"]

    def test_enriches_participants_when_enabled(self, mock_client):
        with patch("arbitration.search_ani_mentions", return_value=[]):
            with patch("arbitration.time.sleep"):
                result = fetch_full_arbitration_case(
                    mock_client,
                    "Test",
                    enrich_participants=True,
                    enrich_articles=False,
                    include_ani=False,
                    include_drn=False,
                )

        # Should have called get_users_info
        mock_client.get_users_info.assert_called()
        assert len(result["participants"]) > 0

    def test_enriches_articles_when_enabled(self, mock_client):
        with patch("arbitration.search_ani_mentions", return_value=[]):
            with patch("arbitration.time.sleep"):
                result = fetch_full_arbitration_case(
                    mock_client,
                    "Test",
                    enrich_participants=False,
                    enrich_articles=True,
                    max_articles=5,
                    include_ani=False,
                    include_drn=False,
                )

        # Should have called get_page_assessments
        mock_client.get_page_assessments.assert_called()

    def test_summary_contains_counts(self, mock_client):
        with patch("arbitration.search_ani_mentions", return_value=[]):
            with patch("arbitration.time.sleep"):
                result = fetch_full_arbitration_case(
                    mock_client,
                    "Test",
                    enrich_participants=False,
                    enrich_articles=False,
                    include_ani=False,
                    include_drn=False,
                )

        summary = result["summary"]
        assert "case_pages_found" in summary
        assert "participants_extracted" in summary
        assert "articles_extracted" in summary
