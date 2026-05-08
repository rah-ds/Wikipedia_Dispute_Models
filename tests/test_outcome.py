"""Tests for src.outcome module — ArbCom decision parser."""

from src.outcome import (
    DecisionOutcome,
    ProposalItem,
    VoteTally,
    parse_decision,
    _extract_voters,
    _parse_votes_from_section,
)


# ---------------------------------------------------------------------------
# Fixtures — realistic wikitext fragments
# ---------------------------------------------------------------------------

SAMPLE_FINDING = """\
===Locus of dispute===
1) This dispute revolves around Wikipedia's coverage of [[climate change]].

:Support:
:# Standard. [[User:Newyorkbrad|Newyorkbrad]] 01:08, 2 September 2010 (UTC)
:# [[User:Roger Davies|Roger Davies]] 11:42, 11 September 2010 (UTC)
:# [[User:Shell Kinney|Shell]] 12:01, 11 September 2010 (UTC)
:# [[User:Mailer diablo|Mailer Diablo]] 18:10, 25 September 2010 (UTC)
:# [[User:Risker|Risker]] 00:36, 27 September 2010 (UTC)

:Oppose:
:#

:Abstain:
:#
"""

SAMPLE_REMEDY = """\
===William M. Connolley topic-banned===
5.6) [[User:William M. Connolley]] is topic-banned from Climate change.

:Support:
:# To replace remedies 5.1 to 5.5. [[User:Roger Davies|Roger Davies]] 04:18, 24 September 2010 (UTC)
:# [[User:Shell Kinney|Shell]] 08:51, 26 September 2010 (UTC)
:# [[User:Coren|Coren]] 17:52, 2 October 2010 (UTC)
:# [[User:Risker|Risker]] 19:54, 2 October 2010 (UTC)
:# [[User:Carcharoth|Carcharoth]] 07:40, 8 October 2010 (UTC)
:# [[User:Mailer diablo|Mailer Diablo]] 15:50, 9 October 2010 (UTC)
:# [[User:Newyorkbrad|Newyorkbrad]] 20:13, 10 October 2010 (UTC)

:Oppose:
:#

:Abstain:
:#
"""

SAMPLE_FAILED_ITEM = """\
===William M. Connolley banned===
5.1) [[User:William M. Connolley]] is banned for six months.

:Support:
:#

:Oppose:
:# I will not be supporting this one. [[User:Newyorkbrad|Newyorkbrad]] 01:45, 2 September 2010 (UTC)
:# Not necessary. [[User:Kirill Lokshin|Kirill]] 18:28, 5 September 2010 (UTC)
:# Overkill. [[User:Coren|Coren]] 00:52, 6 September 2010 (UTC)
:# [[User:Shell Kinney|Shell]] 08:09, 6 September 2010 (UTC)
:# [[User:Roger Davies|Roger Davies]] 04:01, 24 September 2010 (UTC)
:# [[User:Mailer diablo|Mailer Diablo]] 15:50, 9 October 2010 (UTC)

:Abstain:
:#
"""

# A complete mini-page with multiple sections
SAMPLE_FULL_PAGE = f"""\
==Proposed principles==

===Purpose of Wikipedia===
1) The purpose of Wikipedia is to create a high-quality encyclopedia.

:Support:
:# [[User:Alice|Alice]] 01:00, 1 January 2024 (UTC)
:# [[User:Bob|Bob]] 02:00, 1 January 2024 (UTC)
:# [[User:Charlie|Charlie]] 03:00, 1 January 2024 (UTC)
:# [[User:Dana|Dana]] 04:00, 1 January 2024 (UTC)
:# [[User:Eve|Eve]] 05:00, 1 January 2024 (UTC)

:Oppose:
:#

:Abstain:
:#

==Proposed findings of fact==

{SAMPLE_FINDING}

==Proposed remedies==

{SAMPLE_REMEDY}

{SAMPLE_FAILED_ITEM}

==Discussion by Arbitrators==
===General===
This section is meta-discussion and should be skipped.

==Motion to close==
===Implementation notes===
Also skipped.
"""


# ---------------------------------------------------------------------------
# _extract_voters tests
# ---------------------------------------------------------------------------


class TestExtractVoters:
    def test_basic_voter_extraction(self):
        text = """\
:# Comment. [[User:Alice|Alice]] 01:00, 1 Jan 2024 (UTC)
:# [[User:Bob|Bob]] 02:00, 1 Jan 2024 (UTC)
"""
        voters = _extract_voters(text)
        assert voters == ["Alice", "Bob"]

    def test_empty_vote_lines_ignored(self):
        text = """\
:#
:#
"""
        voters = _extract_voters(text)
        assert voters == []

    def test_user_talk_links(self):
        text = """\
:# [[User talk:Alice|talk]] and [[User:Alice|Alice]] 01:00, 1 Jan 2024 (UTC)
"""
        voters = _extract_voters(text)
        # Should deduplicate Alice from User: and User talk: links
        assert voters == ["Alice"]

    def test_non_vote_lines_ignored(self):
        text = """\
Some random text with [[User:Ignored|Ignored]]
:# [[User:Counted|Counted]] 01:00, 1 Jan 2024 (UTC)
:: Indented comment [[User:AlsoIgnored|AlsoIgnored]]
"""
        voters = _extract_voters(text)
        assert voters == ["Counted"]

    def test_nested_colons(self):
        """ArbCom pages sometimes use ::# for sub-votes."""
        text = """\
::# [[User:DeepVoter|DeepVoter]] 01:00, 1 Jan 2024 (UTC)
"""
        voters = _extract_voters(text)
        assert voters == ["DeepVoter"]


# ---------------------------------------------------------------------------
# _parse_votes_from_section tests
# ---------------------------------------------------------------------------


class TestParseVotesFromSection:
    def test_simple_section(self):
        tally = _parse_votes_from_section(SAMPLE_FINDING)
        assert tally.support == 5
        assert tally.oppose == 0
        assert tally.abstain == 0
        assert tally.passed is True
        assert "Newyorkbrad" in tally.support_voters
        assert "Roger Davies" in tally.support_voters

    def test_failed_item(self):
        tally = _parse_votes_from_section(SAMPLE_FAILED_ITEM)
        assert tally.support == 0
        assert tally.oppose == 6
        assert tally.passed is False
        assert tally.net_support == -6

    def test_total_votes(self):
        tally = _parse_votes_from_section(SAMPLE_FINDING)
        assert tally.total_votes == 5  # 5 support, 0 oppose, 0 abstain


# ---------------------------------------------------------------------------
# VoteTally tests
# ---------------------------------------------------------------------------


class TestVoteTally:
    def test_net_support(self):
        t = VoteTally(support=5, oppose=1, abstain=2)
        assert t.net_support == 4
        assert t.passed is True

    def test_not_passed(self):
        t = VoteTally(support=3, oppose=0, abstain=1)
        assert t.net_support == 3
        assert t.passed is False

    def test_edge_case_exactly_four(self):
        t = VoteTally(support=4, oppose=0, abstain=0)
        assert t.passed is True

    def test_empty(self):
        t = VoteTally()
        assert t.total_votes == 0
        assert t.passed is False


# ---------------------------------------------------------------------------
# parse_decision tests
# ---------------------------------------------------------------------------


class TestParseDecision:
    def test_full_page(self):
        outcome = parse_decision(SAMPLE_FULL_PAGE)
        assert isinstance(outcome, DecisionOutcome)
        assert outcome.total_items >= 3  # 1 principle + 1 finding + 2 remedies

    def test_principles_found(self):
        outcome = parse_decision(SAMPLE_FULL_PAGE)
        assert len(outcome.principles) >= 1
        assert outcome.principles[0].kind == "principle"
        assert outcome.principles[0].votes.support == 5

    def test_findings_found(self):
        outcome = parse_decision(SAMPLE_FULL_PAGE)
        assert len(outcome.findings) >= 1
        finding = outcome.findings[0]
        assert "1" in finding.number
        assert finding.votes.support == 5
        assert finding.passed is True

    def test_remedies_found(self):
        outcome = parse_decision(SAMPLE_FULL_PAGE)
        assert len(outcome.remedies) >= 1
        # The passed remedy (5.6)
        passed_remedies = [r for r in outcome.remedies if r.passed]
        assert len(passed_remedies) >= 1

    def test_failed_items_detected(self):
        outcome = parse_decision(SAMPLE_FULL_PAGE)
        failed = outcome.failed_items
        assert any(i.kind == "remedy" for i in failed)

    def test_meta_sections_skipped(self):
        outcome = parse_decision(SAMPLE_FULL_PAGE)
        titles = [i.title.lower() for i in outcome.items]
        assert "general" not in titles
        assert "implementation notes" not in titles

    def test_all_voters(self):
        outcome = parse_decision(SAMPLE_FULL_PAGE)
        voters = outcome.all_voters
        assert "Alice" in voters  # from principle
        assert "Newyorkbrad" in voters  # from finding/remedy

    def test_arbitrator_count(self):
        outcome = parse_decision(SAMPLE_FULL_PAGE)
        assert outcome.arbitrator_count >= 5

    def test_pass_rate(self):
        outcome = parse_decision(SAMPLE_FULL_PAGE)
        # At least 3 passed (principle, finding, remedy 5.6) and 1 failed (remedy 5.1)
        assert 0 < outcome.pass_rate <= 1.0

    def test_to_summary_dict(self):
        outcome = parse_decision(SAMPLE_FULL_PAGE)
        d = outcome.to_summary_dict()
        assert "outcome_total_items" in d
        assert "outcome_pass_rate" in d
        assert "outcome_remedies_passed" in d
        assert "outcome_findings_passed" in d
        assert d["outcome_total_items"] >= 3

    def test_empty_text(self):
        outcome = parse_decision("")
        assert outcome.total_items == 0

    def test_no_votes(self):
        text = """\
==Proposed findings of fact==
===Some finding===
1) Description without any vote sections.
"""
        outcome = parse_decision(text)
        # Items are included even without votes (pre-2012 pages used
        # different vote formats; dropping them caused silent omissions).
        assert outcome.total_items == 1
        assert outcome.items[0].votes.support == 0
        assert outcome.items[0].votes.oppose == 0

    def test_proposal_number_extraction(self):
        outcome = parse_decision(SAMPLE_FULL_PAGE)
        # The passed remedy should have number "5.6"
        remedy_numbers = [r.number for r in outcome.remedies]
        assert "5.6" in remedy_numbers or any("5" in n for n in remedy_numbers)


# ---------------------------------------------------------------------------
# ProposalItem tests
# ---------------------------------------------------------------------------


class TestProposalItem:
    def test_passed_property(self):
        item = ProposalItem(
            kind="finding",
            number="1",
            title="Test",
            body="Test body",
            votes=VoteTally(support=5, oppose=0, abstain=1),
        )
        assert item.passed is True

    def test_failed_property(self):
        item = ProposalItem(
            kind="remedy",
            number="5.1",
            title="Test Remedy",
            body="Remedy body",
            votes=VoteTally(support=0, oppose=6, abstain=0),
        )
        assert item.passed is False


# ---------------------------------------------------------------------------
# DecisionOutcome tests
# ---------------------------------------------------------------------------


class TestDecisionOutcome:
    def test_empty_outcome(self):
        outcome = DecisionOutcome()
        assert outcome.total_items == 0
        assert outcome.pass_rate == 0.0
        assert outcome.all_voters == set()

    def test_summary_dict_empty(self):
        d = DecisionOutcome().to_summary_dict()
        assert d["outcome_total_items"] == 0
        assert d["outcome_pass_rate"] == 0.0


# ---------------------------------------------------------------------------
# Edge case and malformed input tests
# ---------------------------------------------------------------------------


class TestMalformedWikitext:
    """Tests for handling malformed or unusual wikitext."""

    def test_missing_vote_sections(self):
        """Items with only Support but no Oppose/Abstain."""
        text = """\
==Proposed findings of fact==
===Partial votes===
1) Finding with incomplete vote sections.

:Support:
:# [[User:Alice|Alice]] 01:00, 1 Jan 2024 (UTC)
:# [[User:Bob|Bob]] 02:00, 1 Jan 2024 (UTC)
:# [[User:Charlie|Charlie]] 03:00, 1 Jan 2024 (UTC)
:# [[User:Dana|Dana]] 04:00, 1 Jan 2024 (UTC)
"""
        outcome = parse_decision(text)
        assert outcome.total_items == 1
        assert outcome.items[0].votes.support == 4
        assert outcome.items[0].votes.oppose == 0

    def test_irregular_heading_levels(self):
        """Headings jumping from level 2 to level 4."""
        text = """\
==Proposed remedies==
====Deep nested remedy====
1) This skips level 3.

:Support:
:# [[User:A|A]] 01:00, 1 Jan 2024 (UTC)
:# [[User:B|B]] 02:00, 1 Jan 2024 (UTC)
:# [[User:C|C]] 03:00, 1 Jan 2024 (UTC)
:# [[User:D|D]] 04:00, 1 Jan 2024 (UTC)

:Oppose:
:#

:Abstain:
:#
"""
        outcome = parse_decision(text)
        assert outcome.total_items == 1
        assert outcome.items[0].kind == "remedy"

    def test_unicode_usernames(self):
        """Usernames with unicode characters."""
        text = """\
==Proposed findings of fact==
===Unicode test===
1) Test with unicode usernames.

:Support:
:# [[User:Müller|Müller]] 01:00, 1 Jan 2024 (UTC)
:# [[User:日本語|日本語]] 02:00, 1 Jan 2024 (UTC)
:# [[User:Émile|Émile]] 03:00, 1 Jan 2024 (UTC)
:# [[User:Владимир|Владимир]] 04:00, 1 Jan 2024 (UTC)

:Oppose:
:#

:Abstain:
:#
"""
        outcome = parse_decision(text)
        assert outcome.total_items == 1
        voters = outcome.all_voters
        assert "Müller" in voters
        assert "日本語" in voters

    def test_extra_whitespace_in_headings(self):
        """Headings with extra whitespace."""
        text = """\
==  Proposed findings of fact  ==
===   Whitespace test   ===
1) Extra spaces in headings.

:Support:
:# [[User:A|A]] 01:00, 1 Jan 2024 (UTC)
:# [[User:B|B]] 02:00, 1 Jan 2024 (UTC)
:# [[User:C|C]] 03:00, 1 Jan 2024 (UTC)
:# [[User:D|D]] 04:00, 1 Jan 2024 (UTC)

:Oppose:
:#

:Abstain:
:#
"""
        outcome = parse_decision(text)
        assert outcome.total_items == 1

    def test_mixed_case_vote_labels(self):
        """Vote labels with mixed case."""
        text = """\
==Proposed remedies==
===Mixed case===
1) Mixed case vote labels.

:SUPPORT:
:# [[User:A|A]] 01:00, 1 Jan 2024 (UTC)
:# [[User:B|B]] 02:00, 1 Jan 2024 (UTC)
:# [[User:C|C]] 03:00, 1 Jan 2024 (UTC)
:# [[User:D|D]] 04:00, 1 Jan 2024 (UTC)

:oppose:
:#

:AbStAiN:
:#
"""
        outcome = parse_decision(text)
        assert outcome.total_items == 1
        assert outcome.items[0].votes.support == 4

    def test_comments_in_vote_lines(self):
        """Vote lines with long comments before/after username."""
        text = """\
==Proposed findings of fact==
===Comments test===
1) Test.

:Support:
:# This is a long comment before the link. [[User:Alice|Alice]] 01:00, 1 Jan 2024 (UTC)
:# [[User:Bob|Bob]] said something 02:00, 1 Jan 2024 (UTC) with trailing comment.
:# Per above. [[User:Charlie|Charlie]] 03:00, 1 Jan 2024 (UTC)
:# I strongly support this. [[User:Dana|Dana]] 04:00, 1 Jan 2024 (UTC)

:Oppose:
:#

:Abstain:
:#
"""
        outcome = parse_decision(text)
        assert outcome.items[0].votes.support == 4
        assert "Alice" in outcome.items[0].votes.support_voters

    def test_multiple_users_same_line(self):
        """Multiple user links on the same vote line (should get first)."""
        text = """\
==Proposed findings of fact==
===Multi-user===
1) Test.

:Support:
:# [[User:Primary|Primary]] agrees with [[User:Secondary|Secondary]] 01:00, 1 Jan 2024 (UTC)
:# [[User:Another|Another]] 02:00, 1 Jan 2024 (UTC)
:# [[User:Third|Third]] 03:00, 1 Jan 2024 (UTC)
:# [[User:Fourth|Fourth]] 04:00, 1 Jan 2024 (UTC)

:Oppose:
:#

:Abstain:
:#
"""
        outcome = parse_decision(text)
        voters = outcome.items[0].votes.support_voters
        assert "Primary" in voters
        assert "Secondary" in voters  # Both should be extracted

    def test_no_headings(self):
        """Wikitext with no headings at all."""
        text = "Just some plain text without any structure."
        outcome = parse_decision(text)
        assert outcome.total_items == 0

    def test_only_level2_headings(self):
        """Only top-level headings, no items."""
        text = """\
==Proposed findings of fact==
Some text but no sub-items.
==Proposed remedies==
More text but still no items.
"""
        outcome = parse_decision(text)
        assert outcome.total_items == 0

    def test_body_truncation(self):
        """Long body text should be truncated."""
        long_body = "X" * 1000
        text = f"""\
==Proposed findings of fact==
===Long body===
1) {long_body}

:Support:
:# [[User:A|A]] 01:00, 1 Jan 2024 (UTC)
:# [[User:B|B]] 02:00, 1 Jan 2024 (UTC)
:# [[User:C|C]] 03:00, 1 Jan 2024 (UTC)
:# [[User:D|D]] 04:00, 1 Jan 2024 (UTC)

:Oppose:
:#

:Abstain:
:#
"""
        outcome = parse_decision(text)
        assert len(outcome.items[0].body) <= 500

    def test_enforcement_section(self):
        """Test that enforcement section type is detected."""
        text = """\
==Proposed enforcement==
===Enforcement provision===
1) This is an enforcement provision.

:Support:
:# [[User:A|A]] 01:00, 1 Jan 2024 (UTC)
:# [[User:B|B]] 02:00, 1 Jan 2024 (UTC)
:# [[User:C|C]] 03:00, 1 Jan 2024 (UTC)
:# [[User:D|D]] 04:00, 1 Jan 2024 (UTC)

:Oppose:
:#

:Abstain:
:#
"""
        outcome = parse_decision(text)
        assert len(outcome.enforcement) == 1
        assert outcome.items[0].kind == "enforcement"


class TestVoteTallyEdgeCases:
    """Additional edge case tests for VoteTally."""

    def test_all_abstain(self):
        """All votes are abstain."""
        t = VoteTally(support=0, oppose=0, abstain=5)
        assert t.net_support == 0
        assert t.passed is False
        assert t.total_votes == 5

    def test_tie_vote(self):
        """Equal support and oppose."""
        t = VoteTally(support=3, oppose=3, abstain=2)
        assert t.net_support == 0
        assert t.passed is False

    def test_negative_net_support(self):
        """More oppose than support."""
        t = VoteTally(support=1, oppose=5, abstain=0)
        assert t.net_support == -4
        assert t.passed is False
