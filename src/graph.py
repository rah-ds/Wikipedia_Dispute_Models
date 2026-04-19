"""
Graph construction for Wikipedia dispute data.

Builds a NetworkX MultiDiGraph from ArbitrationCaseSummary objects where:

Node types:
    editor   – Wikipedia editors involved in disputes
    article  – Disputed articles
    arbcase  – Arbitration cases

Edge types:
    REVERTS      – Editor → Editor  (directed revert relationship)
    EDITS_CASE   – Editor → ArbCase (participation in a case)
    EDITS_ARTICLE– Editor → Article (editing an article in dispute)
    SUBJECT_OF   – Article → ArbCase (article is subject of a case)
    CO_OCCURS    – Editor ↔ Editor  (appear together in 2+ cases)

Usage:
    from src.arbitration import load_all_cases
    from src.graph import build_cross_case_graph, graph_summary

    cases = load_all_cases()
    G = build_cross_case_graph(cases)
    print(graph_summary(G))
"""

from __future__ import annotations

from collections import Counter, defaultdict

import networkx as nx

from src.arbitration import ArbitrationCaseSummary


# ---------------------------------------------------------------------------
# Single-case graph
# ---------------------------------------------------------------------------


def build_case_graph(case: ArbitrationCaseSummary) -> nx.MultiDiGraph:
    """Build a graph from a single arbitration case.

    Nodes:
        - One ``editor`` node per editor in the case
        - One ``arbcase`` node for the case itself
        - One ``article`` node per linked article

    Edges:
        - ``REVERTS``       from each ConflictEdge
        - ``EDITS_CASE``    editor → case
        - ``EDITS_ARTICLE`` editor → article (if article revision data exists)
        - ``SUBJECT_OF``    article → case
    """
    G = nx.MultiDiGraph()

    case_id = f"case:{case.case_name}"

    # Case node
    G.add_node(
        case_id,
        node_type="arbcase",
        label=case.case_name,
        case_prefix=case.case_prefix,
        duration_days=case.case_duration_days,
        total_editors=case.total_editors,
        total_revisions=case.total_revisions,
        earliest=case.earliest_activity,
        latest=case.latest_activity,
    )

    # Editor nodes + EDITS_CASE edges
    for username, profile in case.editor_profiles.items():
        editor_id = f"editor:{username}"
        if not G.has_node(editor_id):
            G.add_node(
                editor_id,
                node_type="editor",
                label=username,
            )
        # Merge profile stats onto existing node
        _merge_editor_attrs(G.nodes[editor_id], profile)

        G.add_edge(
            editor_id,
            case_id,
            edge_type="EDITS_CASE",
            edit_count=profile.total_edits,
            revert_count=profile.total_reverts,
            subpages=list(profile.edits_by_subpage.keys()),
            active_days=profile.active_days,
        )

    # Article nodes + SUBJECT_OF edges
    for title in case.linked_article_titles:
        article_id = f"article:{title}"
        if not G.has_node(article_id):
            G.add_node(
                article_id,
                node_type="article",
                label=title,
            )
        G.add_edge(
            article_id,
            case_id,
            edge_type="SUBJECT_OF",
        )

    # EDITS_ARTICLE edges (from article revision data if available)
    for page in case.linked_articles:
        article_id = f"article:{page.title}"
        for username in page.editors:
            editor_id = f"editor:{username}"
            if not G.has_node(editor_id):
                # Editor only seen in article data, not case data
                G.add_node(editor_id, node_type="editor", label=username)
            edit_count = sum(1 for r in page.revisions if r.user == username)
            G.add_edge(
                editor_id,
                article_id,
                edge_type="EDITS_ARTICLE",
                edit_count=edit_count,
                case=case.case_name,
            )

    # REVERTS edges
    for edge in case.conflict_edges:
        reverter_id = f"editor:{edge.reverter}"
        reverted_id = f"editor:{edge.reverted}"
        for nid in (reverter_id, reverted_id):
            if not G.has_node(nid):
                G.add_node(nid, node_type="editor", label=nid.split(":", 1)[1])
        G.add_edge(
            reverter_id,
            reverted_id,
            edge_type="REVERTS",
            count=edge.count,
            pages=edge.pages,
            case=case.case_name,
        )

    return G


# ---------------------------------------------------------------------------
# Cross-case graph
# ---------------------------------------------------------------------------


def build_cross_case_graph(
    cases: list[ArbitrationCaseSummary],
) -> nx.MultiDiGraph:
    """Merge multiple case graphs and add cross-case CO_OCCURS edges.

    Editor and article nodes are deduplicated by ID. Attributes are
    accumulated across cases (edit counts summed, pages/cases lists merged).

    CO_OCCURS edges connect editors who appear together in 2+ cases.
    """
    G = nx.MultiDiGraph()

    # Phase 1: merge all per-case graphs
    for case in cases:
        case_g = build_case_graph(case)
        _merge_graph(G, case_g)

    # Phase 2: compute cross-case editor co-occurrence
    editor_cases: dict[str, set[str]] = defaultdict(set)
    for u, v, data in G.edges(data=True):
        if data.get("edge_type") == "EDITS_CASE":
            editor_cases[u].add(v)  # u = editor:X, v = case:Y

    editors = list(editor_cases.keys())
    for i, e1 in enumerate(editors):
        for e2 in editors[i + 1 :]:
            shared = editor_cases[e1] & editor_cases[e2]
            if len(shared) >= 2:
                G.add_edge(
                    e1,
                    e2,
                    edge_type="CO_OCCURS",
                    shared_cases=[c.split(":", 1)[1] for c in shared],
                    shared_count=len(shared),
                )

    # Phase 3: annotate editor nodes with cross-case stats
    for editor_id in editors:
        node = G.nodes[editor_id]
        node["case_count"] = len(editor_cases[editor_id])
        node["cases"] = [c.split(":", 1)[1] for c in editor_cases[editor_id]]

    return G


# ---------------------------------------------------------------------------
# Subgraph projections
# ---------------------------------------------------------------------------


def editor_conflict_subgraph(G: nx.MultiDiGraph) -> nx.DiGraph:
    """Project to a weighted directed graph of editor-to-editor reverts.

    Collapses parallel REVERTS edges into a single edge with total weight.
    """
    H = nx.DiGraph()
    for u, v, data in G.edges(data=True):
        if data.get("edge_type") != "REVERTS":
            continue
        if H.has_edge(u, v):
            H[u][v]["weight"] += data.get("count", 1)
            cases = H[u][v].get("cases", [])
            case = data.get("case", "")
            if case and case not in cases:
                cases.append(case)
                H[u][v]["cases"] = cases
        else:
            H.add_edge(
                u,
                v,
                weight=data.get("count", 1),
                cases=[data["case"]] if data.get("case") else [],
            )
            # Copy node attrs
            for nid in (u, v):
                if nid in G.nodes:
                    H.add_node(nid, **G.nodes[nid])
    return H


def editor_cooccurrence_subgraph(G: nx.MultiDiGraph) -> nx.Graph:
    """Project to an undirected graph of editor co-occurrence.

    Edges exist between editors who appear together in 2+ cases.
    """
    H = nx.Graph()
    for u, v, data in G.edges(data=True):
        if data.get("edge_type") != "CO_OCCURS":
            continue
        if H.has_edge(u, v):
            H[u][v]["weight"] += data.get("shared_count", 1)
        else:
            H.add_edge(
                u,
                v,
                weight=data.get("shared_count", 1),
                shared_cases=data.get("shared_cases", []),
            )
            for nid in (u, v):
                if nid in G.nodes:
                    H.add_node(nid, **G.nodes[nid])
    return H


def article_case_bipartite(G: nx.MultiDiGraph) -> nx.Graph:
    """Project to an undirected bipartite graph of articles and cases.

    Articles and cases are connected by SUBJECT_OF edges.
    """
    B = nx.Graph()
    for u, v, data in G.edges(data=True):
        if data.get("edge_type") != "SUBJECT_OF":
            continue
        B.add_node(u, **G.nodes.get(u, {}))
        B.add_node(v, **G.nodes.get(v, {}))
        B.add_edge(u, v)
    return B


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def graph_summary(G: nx.MultiDiGraph) -> dict:
    """Compute summary statistics for a dispute graph."""
    node_types: Counter[str] = Counter()
    for _, data in G.nodes(data=True):
        node_types[data.get("node_type", "unknown")] += 1

    edge_types: Counter[str] = Counter()
    for _, _, data in G.edges(data=True):
        edge_types[data.get("edge_type", "unknown")] += 1

    return {
        "total_nodes": G.number_of_nodes(),
        "total_edges": G.number_of_edges(),
        "node_types": dict(node_types),
        "edge_types": dict(edge_types),
        "density": nx.density(G),
    }


def top_editors_by_centrality(
    G: nx.MultiDiGraph,
    metric: str = "degree",
    n: int = 20,
) -> list[tuple[str, float]]:
    """Rank editor nodes by a centrality metric.

    Parameters
    ----------
    G : the full dispute graph (or an editor-only projection)
    metric : one of "degree", "betweenness", "pagerank"
    n : number of top editors to return

    Returns
    -------
    List of (editor_id, score) tuples, sorted descending.
    """
    # Filter to editor nodes only
    editor_nodes = [
        nid for nid, d in G.nodes(data=True) if d.get("node_type") == "editor"
    ]
    subgraph = G.subgraph(editor_nodes)

    if metric == "degree":
        scores = dict(subgraph.degree())
    elif metric == "betweenness":
        scores = nx.betweenness_centrality(subgraph)
    elif metric == "pagerank":
        scores = nx.pagerank(subgraph)
    else:
        raise ValueError(
            f"Unknown metric: {metric!r}. Use 'degree', 'betweenness', or 'pagerank'."
        )

    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:n]


def detect_communities(G: nx.MultiDiGraph) -> dict[str, int]:
    """Run Louvain community detection on the editor conflict subgraph.

    Returns a mapping of editor_id → community_id.
    """
    conflict = editor_conflict_subgraph(G)
    if conflict.number_of_nodes() == 0:
        return {}

    # Louvain requires undirected graph
    undirected = conflict.to_undirected()
    return nx.community.louvain_communities(undirected, seed=42)


def serial_disputants(
    G: nx.MultiDiGraph,
    min_cases: int = 2,
) -> list[tuple[str, int, list[str]]]:
    """Find editors who appear in multiple arbitration cases.

    Returns list of (editor_id, case_count, case_names), sorted descending.
    """
    results = []
    for nid, data in G.nodes(data=True):
        if data.get("node_type") != "editor":
            continue
        case_count = data.get("case_count", 0)
        if case_count >= min_cases:
            results.append((nid, case_count, data.get("cases", [])))
    return sorted(results, key=lambda x: x[1], reverse=True)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _merge_editor_attrs(existing: dict, profile) -> None:
    """Accumulate editor stats onto an existing node attrs dict."""
    existing["total_edits"] = existing.get("total_edits", 0) + profile.total_edits
    existing["total_reverts"] = existing.get("total_reverts", 0) + profile.total_reverts
    existing["revert_ratio"] = (
        existing["total_reverts"] / existing["total_edits"]
        if existing["total_edits"]
        else 0.0
    )


def _merge_graph(target: nx.MultiDiGraph, source: nx.MultiDiGraph) -> None:
    """Merge source graph into target, accumulating editor stats."""
    for nid, data in source.nodes(data=True):
        if target.has_node(nid):
            # Accumulate numeric attrs for editor nodes
            if data.get("node_type") == "editor":
                t = target.nodes[nid]
                for key in ("total_edits", "total_reverts"):
                    t[key] = t.get(key, 0) + data.get(key, 0)
                if t.get("total_edits"):
                    t["revert_ratio"] = t["total_reverts"] / t["total_edits"]
        else:
            target.add_node(nid, **data)

    for u, v, key, data in source.edges(keys=True, data=True):
        target.add_edge(u, v, **data)
