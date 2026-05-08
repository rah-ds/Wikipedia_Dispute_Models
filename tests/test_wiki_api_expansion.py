"""Tests for WikiClient API expansion methods."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _make_client():
    """Create a WikiClient with mocked session (no real HTTP)."""
    with patch.dict("os.environ", {"WIKIPEDIA_ACCESS_TOKEN": "test"}):
        from wiki import WikiClient

        client = WikiClient(use_oauth=True)
    return client


class TestEditTags:
    """Tests for edit tags in revision fetching."""

    def test_get_revisions_includes_tags_by_default(self):
        """Verify tags field is included when include_tags=True."""
        client = _make_client()
        client._api_request = MagicMock(
            return_value={
                "query": {
                    "pages": {
                        "1": {
                            "title": "Test Page",
                            "revisions": [
                                {
                                    "revid": 123,
                                    "parentid": 122,
                                    "timestamp": "2024-01-01T00:00:00Z",
                                    "user": "TestUser",
                                    "comment": "Test edit",
                                    "size": 1000,
                                    "tags": ["mw-rollback", "mw-reverted"],
                                }
                            ],
                        }
                    }
                }
            }
        )

        revisions = client.get_revisions("Test Page", limit=1, include_tags=True)

        assert len(revisions) == 1
        assert "tags" in revisions[0]
        assert revisions[0]["tags"] == ["mw-rollback", "mw-reverted"]

    def test_get_revisions_without_tags(self):
        """Verify tags field is excluded when include_tags=False."""
        client = _make_client()
        client._api_request = MagicMock(
            return_value={
                "query": {
                    "pages": {
                        "1": {
                            "title": "Test Page",
                            "revisions": [
                                {
                                    "revid": 123,
                                    "parentid": 122,
                                    "timestamp": "2024-01-01T00:00:00Z",
                                    "user": "TestUser",
                                    "comment": "Test edit",
                                    "size": 1000,
                                }
                            ],
                        }
                    }
                }
            }
        )

        revisions = client.get_revisions("Test Page", limit=1, include_tags=False)

        assert len(revisions) == 1
        assert "tags" not in revisions[0]


class TestUserInfo:
    """Tests for user info fetching."""

    def test_get_user_info_returns_expected_fields(self):
        """Verify get_user_info returns all expected fields."""
        client = _make_client()
        client._api_request = MagicMock(
            return_value={
                "query": {
                    "users": [
                        {
                            "name": "TestUser",
                            "userid": 12345,
                            "editcount": 1000,
                            "registration": "2020-01-01T00:00:00Z",
                            "groups": ["autoconfirmed", "extendedconfirmed"],
                            "gender": "unknown",
                        }
                    ]
                }
            }
        )
        info = client.get_user_info("TestUser")

        assert info is not None
        assert info["username"] == "TestUser"
        assert info["edit_count"] == 1000
        assert info["is_admin"] is False
        assert info["is_bot"] is False
        assert "groups" in info

    def test_get_user_info_admin_detection(self):
        """Verify admin detection works correctly."""
        client = _make_client()
        client._api_request = MagicMock(
            return_value={
                "query": {
                    "users": [
                        {
                            "name": "AdminUser",
                            "userid": 12345,
                            "editcount": 50000,
                            "groups": ["sysop", "bureaucrat"],
                        }
                    ]
                }
            }
        )
        info = client.get_user_info("AdminUser")
        assert info["is_admin"] is True

    def test_get_user_info_missing_user(self):
        """Verify None returned for missing user."""
        client = _make_client()
        client._api_request = MagicMock(
            return_value={
                "query": {
                    "users": [
                        {
                            "name": "NonexistentUser",
                            "missing": "",
                        }
                    ]
                }
            }
        )
        info = client.get_user_info("NonexistentUser")
        assert info is None

    def test_get_users_info_batch(self):
        """Verify batch user info fetching."""
        client = _make_client()
        client._api_request = MagicMock(
            return_value={
                "query": {
                    "users": [
                        {"name": "User1", "userid": 1, "editcount": 100, "groups": []},
                        {"name": "User2", "userid": 2, "editcount": 200, "groups": []},
                    ]
                }
            }
        )
        info = client.get_users_info(["User1", "User2"])

        assert "User1" in info
        assert "User2" in info
        assert info["User1"]["edit_count"] == 100
        assert info["User2"]["edit_count"] == 200


class TestBlockHistory:
    """Tests for block history fetching."""

    def test_get_user_blocks_returns_blocks(self):
        """Verify get_user_blocks returns block data."""
        client = _make_client()
        client._api_request = MagicMock(
            return_value={
                "query": {
                    "blocks": [
                        {
                            "id": 1,
                            "user": "BlockedUser",
                            "by": "AdminUser",
                            "timestamp": "2024-01-01T00:00:00Z",
                            "expiry": "2024-01-08T00:00:00Z",
                            "reason": "Vandalism",
                        }
                    ]
                }
            }
        )
        blocks = client.get_user_blocks("BlockedUser")

        assert len(blocks) == 1
        assert blocks[0]["block_id"] == 1
        assert blocks[0]["blocked_by"] == "AdminUser"
        assert blocks[0]["reason"] == "Vandalism"

    def test_get_block_log_returns_events(self):
        """Verify get_block_log returns log entries."""
        client = _make_client()
        client._api_request = MagicMock(
            return_value={
                "query": {
                    "logevents": [
                        {
                            "logid": 1,
                            "action": "block",
                            "user": "AdminUser",
                            "timestamp": "2024-01-01T00:00:00Z",
                            "comment": "Blocked for vandalism",
                            "params": {
                                "duration": "1 week",
                                "expiry": "2024-01-08T00:00:00Z",
                            },
                        },
                        {
                            "logid": 2,
                            "action": "unblock",
                            "user": "AdminUser",
                            "timestamp": "2024-01-05T00:00:00Z",
                            "comment": "Early unblock",
                            "params": {},
                        },
                    ]
                }
            }
        )
        log = client.get_block_log("BlockedUser")

        assert len(log) == 2
        assert log[0]["action"] == "block"
        assert log[1]["action"] == "unblock"


class TestLogEvents:
    """Tests for log event fetching."""

    def test_get_log_events_filters_by_type(self):
        """Verify log events are filtered by type."""
        client = _make_client()
        client._api_request = MagicMock(
            return_value={
                "query": {
                    "logevents": [
                        {
                            "logid": 1,
                            "type": "protect",
                            "action": "protect",
                            "title": "Test Page",
                            "user": "AdminUser",
                            "timestamp": "2024-01-01T00:00:00Z",
                            "comment": "Protection applied",
                        }
                    ]
                }
            }
        )
        events = client.get_log_events("protect", title="Test Page")

        assert len(events) == 1
        assert events[0]["log_type"] == "protect"
        assert events[0]["action"] == "protect"

    def test_get_protection_log(self):
        """Verify protection log fetching."""
        client = _make_client()
        client._api_request = MagicMock(
            return_value={
                "query": {
                    "logevents": [
                        {
                            "logid": 1,
                            "type": "protect",
                            "action": "protect",
                            "title": "Test Page",
                            "user": "AdminUser",
                            "timestamp": "2024-01-01T00:00:00Z",
                            "params": {
                                "description": "edit=autoconfirmed",
                                "cascade": True,
                            },
                        }
                    ]
                }
            }
        )
        events = client.get_protection_log("Test Page")

        assert len(events) == 1
        assert events[0]["protection_level"] == "edit=autoconfirmed"
        assert events[0]["cascade"] is True


class TestPageAssessments:
    """Tests for page quality assessments."""

    def test_get_page_assessments_returns_ratings(self):
        """Verify page assessments are returned."""
        client = _make_client()
        client._api_request = MagicMock(
            return_value={
                "query": {
                    "pages": {
                        "123": {
                            "title": "Climate change",
                            "pageassessments": {
                                "WikiProject Climate change": {
                                    "class": "B",
                                    "importance": "Top",
                                },
                                "WikiProject Environment": {
                                    "class": "B",
                                    "importance": "High",
                                },
                            },
                        }
                    }
                }
            }
        )
        assessments = client.get_page_assessments("Climate change")

        assert assessments["title"] == "Climate change"
        assert "WikiProject Climate change" in assessments["assessments"]
        assert assessments["highest_quality"] == "B"
        assert assessments["highest_importance"] == "Top"

    def test_get_page_assessments_missing_page(self):
        """Verify empty assessments for missing page."""
        client = _make_client()
        client._api_request = MagicMock(
            return_value={
                "query": {
                    "pages": {
                        "-1": {
                            "ns": 0,
                            "title": "Nonexistent Page",
                            "missing": "",
                        }
                    }
                }
            }
        )
        assessments = client.get_page_assessments("Nonexistent Page")
        assert assessments["assessments"] == {}
