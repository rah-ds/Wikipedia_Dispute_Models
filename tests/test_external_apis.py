"""Tests for external API clients (ORES, Pageviews, XTools)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestOresClient:
    """Tests for ORES/Lift Wing client."""

    def test_ores_score_dataclass(self):
        from ores import OresScore

        score = OresScore(
            revid=123,
            damaging=0.8,
            goodfaith=0.2,
            damaging_prediction=True,
            goodfaith_prediction=False,
        )
        assert score.revid == 123
        assert score.damaging == 0.8
        assert score.goodfaith == 0.2

    def test_ores_client_initialization(self):
        from ores import OresClient

        client = OresClient(wiki="enwiki", use_lift_wing=True)
        assert client.wiki == "enwiki"
        assert client.use_lift_wing is True

    @patch("ores.requests.Session")
    def test_get_scores_returns_empty_for_empty_list(self, mock_session):
        from ores import OresClient

        client = OresClient()
        scores = client.get_scores([])
        assert scores == {}

    @patch("ores.requests.Session")
    def test_legacy_ores_parsing(self, mock_session):
        from ores import OresClient

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "enwiki": {
                "scores": {
                    "123": {
                        "damaging": {
                            "score": {
                                "probability": {"true": 0.3, "false": 0.7},
                                "prediction": False,
                            }
                        },
                        "goodfaith": {
                            "score": {
                                "probability": {"true": 0.9, "false": 0.1},
                                "prediction": True,
                            }
                        },
                    }
                }
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_session.return_value.get.return_value = mock_response

        client = OresClient(use_lift_wing=False)
        scores = client.get_scores([123])

        assert 123 in scores
        assert scores[123].damaging == 0.3
        assert scores[123].goodfaith == 0.9

    def test_get_revision_quality_function(self):
        from ores import get_revision_quality, OresClient

        with patch.object(OresClient, "get_scores") as mock_get_scores:
            from ores import OresScore

            mock_get_scores.return_value = {
                123: OresScore(revid=123, damaging=0.8, goodfaith=0.3)
            }

            result = get_revision_quality([123])

            assert 123 in result
            assert result[123]["likely_damaging"] is True
            assert result[123]["likely_bad_faith"] is True


class TestPageviewsClient:
    """Tests for Pageviews API client."""

    def test_pageview_data_compute_stats(self):
        from pageviews import PageviewData

        data = PageviewData(
            title="Test",
            views=[
                {"views": 100},
                {"views": 200},
                {"views": 150},
            ],
        )
        data.compute_stats()

        assert data.total_views == 450
        assert data.avg_daily_views == 150.0
        assert data.max_daily_views == 200
        assert data.min_daily_views == 100

    def test_pageviews_client_initialization(self):
        from pageviews import PageviewsClient

        client = PageviewsClient(project="en.wikipedia")
        assert client.project == "en.wikipedia"

    def test_encode_title(self):
        from pageviews import PageviewsClient

        client = PageviewsClient()
        encoded = client._encode_title("Climate change")
        assert " " not in encoded
        assert encoded == "Climate_change"

    @patch("pageviews.requests.Session")
    def test_get_article_views(self, mock_session):
        from pageviews import PageviewsClient

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "items": [
                {"timestamp": "2024010100", "views": 1000},
                {"timestamp": "2024010200", "views": 1200},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_session.return_value.get.return_value = mock_response

        client = PageviewsClient()
        data = client.get_article_views("Test", "20240101", "20240102")

        assert len(data.views) == 2
        assert data.total_views == 2200

    def test_get_article_traffic_function(self):
        from pageviews import get_article_traffic, PageviewsClient, PageviewData

        with patch.object(PageviewsClient, "get_views_last_n_days") as mock_get:
            mock_data = PageviewData(
                title="Test",
                views=[{"views": 100}],
                total_views=100,
                avg_daily_views=100.0,
                max_daily_views=100,
                min_daily_views=100,
            )
            mock_get.return_value = mock_data

            result = get_article_traffic("Test", days=1)

            assert result["title"] == "Test"
            assert result["total_views"] == 100


class TestXToolsClient:
    """Tests for XTools API client."""

    def test_user_stats_dataclass(self):
        from xtools import UserStats

        stats = UserStats(
            username="TestUser",
            total_edit_count=1000,
            is_admin=True,
        )
        assert stats.username == "TestUser"
        assert stats.total_edit_count == 1000
        assert stats.is_admin is True

    def test_xtools_client_initialization(self):
        from xtools import XToolsClient

        client = XToolsClient(project="en.wikipedia.org")
        assert client.project == "en.wikipedia.org"

    def test_encode_username(self):
        from xtools import XToolsClient

        client = XToolsClient()
        encoded = client._encode_username("Test User")
        assert " " not in encoded

    @patch("xtools.requests.Session")
    def test_get_user_stats(self, mock_session):
        from xtools import XToolsClient

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "live_edit_count": 900,
            "deleted_edit_count": 100,
            "user_groups": ["autoconfirmed", "sysop"],
        }
        mock_response.raise_for_status = MagicMock()
        mock_session.return_value.get.return_value = mock_response

        client = XToolsClient()
        stats = client.get_user_stats("TestUser")

        assert stats.username == "TestUser"
        assert stats.total_edit_count == 1000
        assert stats.live_edit_count == 900
        assert stats.is_admin is True

    @patch("xtools.requests.Session")
    def test_get_user_stats_not_found(self, mock_session):
        from xtools import XToolsClient
        import requests

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )
        mock_session.return_value.get.return_value = mock_response

        client = XToolsClient()
        stats = client.get_user_stats("NonexistentUser")

        assert stats.error is not None
        assert "not found" in stats.error

    def test_get_user_summary_function(self):
        from xtools import get_user_summary, XToolsClient, UserStats

        with patch.object(XToolsClient, "get_user_stats") as mock_get:
            mock_stats = UserStats(
                username="TestUser",
                total_edit_count=1000,
                live_edit_count=900,
                deleted_edit_count=100,
                is_admin=True,
                user_groups=["sysop"],
            )
            mock_get.return_value = mock_stats

            result = get_user_summary("TestUser")

            assert result["username"] == "TestUser"
            assert result["total_edits"] == 1000
            assert result["is_admin"] is True
