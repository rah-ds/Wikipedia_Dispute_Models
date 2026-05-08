"""Tests for src.graph module."""

import pytest
import networkx as nx

from src.arbitration import ArbitrationCaseSummary
from src.graph import (
    build_case_graph,
    build_cross_case_graph,
    editor_conflict_subgraph,
    editor_cooccurrence_subgraph,
    article_case_bipartite,
    graph_summary,
    top_editors_by_centrality,
    detect_communities,
    serial_disputants,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CASE_A = {
    "case_name": "Alpha Dispute",
    "case_prefix": "Wikipedia:Arbitration/Requests/Case/Alpha Dispute",
    "fetched_at": "2026-01-01T00:00:00",
    "case_pages": [
        {
            "title": "Wikipedia:Arbitration/Requests/Case/Alpha Dispute",
            "url": "https://en.wikipedia.org/wiki/Alpha",
            "subpage": "(main)",
            "exists": True,
            "revisions": [
                {
                    "revid": 1,
                    "parentid": None,
                    "timestamp": "2024-01-01T00:00:00Z",
                    "user": "Alice",
                    "comment": "Initial filing",
                    "size": 1000,
                },
                {
                    "revid": 2,
                    "parentid": 1,
                    "timestamp": "2024-01-02T00:00:00Z",
                    "user": "Bob",
                    "comment": "Reverted edits by Alice",
                    "size": 950,
                },
                {
                    "revid": 3,
                    "parentid": 2,
                    "timestamp": "2024-01-03T00:00:00Z",
                    "user": "Alice",
                    "comment": "Undid revision by Bob",
                    "size": 1100,
                },
                {
                    "revid": 4,
                    "parentid": 3,
                    "timestamp": "2024-01-04T00:00:00Z",
                    "user": "Charlie",
                    "comment": "Added evidence",
                    "size": 1200,
                },
            ],
        },
    ],
    "case_talk_pages": [],
    "linked_articles": [
        {
            "title": "Foo article",
            "url": "https://en.wikipedia.org/wiki/Foo_article",
            "subpage": "",
            "exists": True,
            "revisions": [
                {
                    "revid": 100,
                    "parentid": None,
                    "timestamp": "2024-01-01T00:00:00Z",
                    "user": "Alice",
                    "comment": "Edited content",
                    "size": 5000,
                },
            ],
        },
    ],
    "article_talk_pages": [],
    "summary": {},
}

CASE_B = {
    "case_name": "Beta Dispute",
    "case_prefix": "Wikipedia:Arbitration/Requests/Case/Beta Dispute",
    "fetched_at": "2026-02-01T00:00:00",
    "case_pages": [
        {
            "title": "Wikipedia:Arbitration/Requests/Case/Beta Dispute",
            "url": "https://en.wikipedia.org/wiki/Beta",
            "subpage": "(main)",
            "exists": True,
            "revisions": [
                {
                    "revid": 10,
                    "parentid": None,
                    "timestamp": "2024-06-01T00:00:00Z",
                    "user": "Alice",
                    "comment": "Filing for Beta case",
                    "size": 800,
                },
                {
                    "revid": 11,
                    "parentid": 10,
                    "timestamp": "2024-06-02T00:00:00Z",
                    "user": "Dave",
                    "comment": "Revert vandalism",
                    "size": 750,
                },
            ],
        },
    ],
    "case_talk_pages": [],
    "linked_articles": [
        {
            "title": "Bar article",
            "url": "https://en.wikipedia.org/wiki/Bar_article",
            "subpage": "",
            "exists": True,
            "revisions": [],
        },
    ],
    "article_talk_pages": [],
    "summary": {},
}

CASE_C = {
    "case_name": "Gamma Dispute",
    "case_prefix": "Wikipedia:Arbitration/Requests/Case/Gamma Dispute",
    "fetched_at": "2026-03-01T00:00:00",
    "case_pages": [
        {
            "title": "Wikipedia:Arbitration/Requests/Case/Gamma Dispute",
            "url": "https://en.wikipedia.org/wiki/Gamma",
            "subpage": "(main)",
            "exists": True,
            "revisions": [
                {
                    "revid": 20,
                    "parentid": None,
                    "timestamp": "2024-09-01T00:00:00Z",
                    "user": "Alice",
                    "comment": "Third case",
                    "size": 900,
                },
                {
                    "revid": 21,
                    "parentid": 20,
                    "timestamp": "2024-09-02T00:00:00Z",
                    "user": "Bob",
                    "comment": "Also in gamma",
                    "size": 950,
                },
            ],
        },
    ],
    "case_talk_pages": [],
    "linked_articles": [
        {
            "title": "Foo article",
            "url": "https://en.wikipedia.org/wiki/Foo_article",
            "subpage": "",
            "exists": True,
            "revisions": [],
        },
    ],
    "article_talk_pages": [],
    "summary": {},
}


@pytest.fixture
def case_a():
    return ArbitrationCaseSummary.from_dict(CASE_A)


@pytest.fixture
def case_b():
    return ArbitrationCaseSummary.from_dict(CASE_B)


@pytest.fixture
def case_c():
    return ArbitrationCaseSummary.from_dict(CASE_C)


@pytest.fixture
def all_cases(case_a, case_b, case_c):
    return [case_a, case_b, case_c]


# ---------------------------------------------------------------------------
# Single-case graph tests
# ---------------------------------------------------------------------------


class TestBuildCaseGraph:
    def test_node_types(self, case_a):
        G = build_case_graph(case_a)
        types = {d["node_type"] for _, d in G.nodes(data=True)}
        assert "editor" in types
        assert "arbcase" in types
        assert "article" in types

    def test_editor_count(self, case_a):
        G = build_case_graph(case_a)
        editors = [n for n, d in G.nodes(data=True) if d["node_type"] == "editor"]
        assert len(editors) == 3  # Alice, Bob, Charlie

    def test_case_node(self, case_a):
        G = build_case_graph(case_a)
        case_id = "case:Alpha Dispute"
        assert G.has_node(case_id)
        assert G.nodes[case_id]["node_type"] == "arbcase"
        assert G.nodes[case_id]["label"] == "Alpha Dispute"

    def test_article_node(self, case_a):
        G = build_case_graph(case_a)
        assert G.has_node("article:Foo article")
        assert G.nodes["article:Foo article"]["node_type"] == "article"

    def test_edits_case_edges(self, case_a):
        G = build_case_graph(case_a)
        edits_case = [
            (u, v, d)
            for u, v, d in G.edges(data=True)
            if d["edge_type"] == "EDITS_CASE"
        ]
        assert len(edits_case) == 3  # Alice, Bob, Charlie each → case

    def test_subject_of_edge(self, case_a):
        G = build_case_graph(case_a)
        subject_edges = [
            (u, v) for u, v, d in G.edges(data=True) if d["edge_type"] == "SUBJECT_OF"
        ]
        assert ("article:Foo article", "case:Alpha Dispute") in subject_edges

    def test_reverts_edges(self, case_a):
        G = build_case_graph(case_a)
        revert_edges = [
            (u, v, d) for u, v, d in G.edges(data=True) if d["edge_type"] == "REVERTS"
        ]
        assert len(revert_edges) >= 1
        # Bob reverted Alice
        reverters = {(u, v) for u, v, d in revert_edges}
        assert ("editor:Bob", "editor:Alice") in reverters

    def test_edits_article_edges(self, case_a):
        G = build_case_graph(case_a)
        art_edges = [
            (u, v, d)
            for u, v, d in G.edges(data=True)
            if d["edge_type"] == "EDITS_ARTICLE"
        ]
        # Alice edited Foo article
        assert any(
            u == "editor:Alice" and v == "article:Foo article" for u, v, d in art_edges
        )


# ---------------------------------------------------------------------------
# Cross-case graph tests
# ---------------------------------------------------------------------------


class TestBuildCrossCaseGraph:
    def test_deduplicates_editors(self, all_cases):
        G = build_cross_case_graph(all_cases)
        alice_nodes = [n for n in G.nodes() if n == "editor:Alice"]
        assert len(alice_nodes) == 1

    def test_accumulates_edits(self, all_cases):
        G = build_cross_case_graph(all_cases)
        alice = G.nodes["editor:Alice"]
        # Alice: 2 case edits (A) + 1 article edit (A) + 1 edit (B) + 1 edit (C) = 5
        assert alice["total_edits"] == 5

    def test_deduplicates_articles(self, all_cases):
        G = build_cross_case_graph(all_cases)
        foo_nodes = [n for n in G.nodes() if n == "article:Foo article"]
        assert len(foo_nodes) == 1

    def test_all_cases_present(self, all_cases):
        G = build_cross_case_graph(all_cases)
        case_nodes = [n for n, d in G.nodes(data=True) if d["node_type"] == "arbcase"]
        assert len(case_nodes) == 3

    def test_co_occurs_edges(self, all_cases):
        """Alice appears in all 3 cases, Bob in 2. They should CO_OCCUR."""
        G = build_cross_case_graph(all_cases)
        co_edges = [
            (u, v, d) for u, v, d in G.edges(data=True) if d["edge_type"] == "CO_OCCURS"
        ]
        # Alice+Bob share Alpha + Gamma (2 cases)
        alice_bob = [
            (u, v) for u, v, d in co_edges if {u, v} == {"editor:Alice", "editor:Bob"}
        ]
        assert len(alice_bob) >= 1

    def test_case_count_attribute(self, all_cases):
        G = build_cross_case_graph(all_cases)
        assert G.nodes["editor:Alice"]["case_count"] == 3
        assert G.nodes["editor:Bob"]["case_count"] == 2


# ---------------------------------------------------------------------------
# Subgraph projection tests
# ---------------------------------------------------------------------------


class TestSubgraphProjections:
    def test_conflict_subgraph_only_editors(self, case_a):
        G = build_case_graph(case_a)
        H = editor_conflict_subgraph(G)
        for n, d in H.nodes(data=True):
            assert d.get("node_type") == "editor"

    def test_conflict_subgraph_weighted(self, case_a):
        G = build_case_graph(case_a)
        H = editor_conflict_subgraph(G)
        # Should have weighted edges
        for u, v, d in H.edges(data=True):
            assert "weight" in d
            assert d["weight"] >= 1

    def test_cooccurrence_subgraph_undirected(self, all_cases):
        G = build_cross_case_graph(all_cases)
        H = editor_cooccurrence_subgraph(G)
        assert isinstance(H, nx.Graph)
        assert not isinstance(H, nx.DiGraph)

    def test_article_case_bipartite(self, all_cases):
        G = build_cross_case_graph(all_cases)
        B = article_case_bipartite(G)
        articles = [n for n, d in B.nodes(data=True) if d.get("node_type") == "article"]
        cases = [n for n, d in B.nodes(data=True) if d.get("node_type") == "arbcase"]
        assert len(articles) >= 2  # Foo, Bar
        assert len(cases) >= 2


# ---------------------------------------------------------------------------
# Metrics tests
# ---------------------------------------------------------------------------


class TestMetrics:
    def test_graph_summary_keys(self, case_a):
        G = build_case_graph(case_a)
        s = graph_summary(G)
        assert "total_nodes" in s
        assert "total_edges" in s
        assert "node_types" in s
        assert "edge_types" in s
        assert "density" in s

    def test_graph_summary_counts(self, case_a):
        G = build_case_graph(case_a)
        s = graph_summary(G)
        assert s["total_nodes"] > 0
        assert s["total_edges"] > 0
        assert s["node_types"]["editor"] == 3
        assert s["node_types"]["arbcase"] == 1

    def test_top_editors_by_degree(self, all_cases):
        G = build_cross_case_graph(all_cases)
        top = top_editors_by_centrality(G, metric="degree", n=5)
        assert len(top) <= 5
        assert all(isinstance(score, (int, float)) for _, score in top)
        # Scores should be descending
        scores = [s for _, s in top]
        assert scores == sorted(scores, reverse=True)

    def test_top_editors_invalid_metric(self, case_a):
        G = build_case_graph(case_a)
        with pytest.raises(ValueError, match="Unknown metric"):
            top_editors_by_centrality(G, metric="invalid")

    def test_serial_disputants(self, all_cases):
        G = build_cross_case_graph(all_cases)
        serial = serial_disputants(G, min_cases=2)
        # Alice (3 cases) and Bob (2 cases)
        names = {nid for nid, _, _ in serial}
        assert "editor:Alice" in names
        assert "editor:Bob" in names

    def test_serial_disputants_min_cases(self, all_cases):
        G = build_cross_case_graph(all_cases)
        serial = serial_disputants(G, min_cases=3)
        names = {nid for nid, _, _ in serial}
        assert "editor:Alice" in names
        assert "editor:Bob" not in names  # Bob only in 2

    def test_detect_communities(self, case_a):
        G = build_case_graph(case_a)
        communities = detect_communities(G)
        # Should return a list of sets (or empty if no conflict edges)
        assert isinstance(communities, (list, dict))


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_case(self):
        empty = {
            "case_name": "Empty",
            "case_prefix": "Wikipedia:Arbitration/Requests/Case/Empty",
            "fetched_at": "2026-01-01T00:00:00",
            "case_pages": [],
            "case_talk_pages": [],
            "linked_articles": [],
            "article_talk_pages": [],
            "summary": {},
        }
        case = ArbitrationCaseSummary.from_dict(empty)
        G = build_case_graph(case)
        # Should have just the case node
        assert G.number_of_nodes() == 1
        assert G.nodes["case:Empty"]["node_type"] == "arbcase"

    def test_cross_case_empty(self):
        G = build_cross_case_graph([])
        assert G.number_of_nodes() == 0
        assert G.number_of_edges() == 0

    def test_single_case_no_co_occurs(self, case_a):
        G = build_cross_case_graph([case_a])
        co_edges = [
            d for _, _, d in G.edges(data=True) if d["edge_type"] == "CO_OCCURS"
        ]
        assert len(co_edges) == 0  # Need 2+ shared cases for CO_OCCURS
