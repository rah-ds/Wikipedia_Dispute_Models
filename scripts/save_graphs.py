"""Save all graph exploration figures to artifacts/graphs/."""

from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx

from src.arbitration import load_all_cases
from src.graph import (
    build_case_graph,
    build_cross_case_graph,
    graph_summary,
    editor_conflict_subgraph,
    article_case_bipartite,
    detect_communities,
    serial_disputants,
)

OUT = Path(__file__).resolve().parent.parent / "artifacts" / "graphs"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    cases = load_all_cases()
    print(f"Loaded {len(cases)} cases")

    G = build_cross_case_graph(cases)
    summary = graph_summary(G)
    print(f"Graph: {summary['total_nodes']:,} nodes, {summary['total_edges']:,} edges")

    # 1. Editor revert degree
    conflict_g = editor_conflict_subgraph(G)
    if conflict_g.number_of_nodes() > 0:
        degree_scores = sorted(
            dict(conflict_g.degree(weight="weight")).items(),
            key=lambda kv: kv[1],
            reverse=True,
        )[:20]
        fig, ax = plt.subplots(figsize=(10, 6))
        labels = [nid.replace("editor:", "") for nid, _ in degree_scores]
        values = [v for _, v in degree_scores]
        ax.barh(labels[::-1], values[::-1])
        ax.set_xlabel("Weighted Degree (total reverts)")
        ax.set_title("Top 20 Editors by Revert Involvement")
        plt.tight_layout()
        fig.savefig(OUT / "editor_revert_degree.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        print("  -> editor_revert_degree.png")

    # 2. Betweenness centrality (approximate — full is too slow on 13K+ editors)
    editor_nodes = [
        nid for nid, d in G.nodes(data=True) if d.get("node_type") == "editor"
    ]
    editor_sub = G.subgraph(editor_nodes)
    bc_scores = nx.betweenness_centrality(editor_sub, k=min(200, len(editor_nodes)))
    top_betweenness = sorted(bc_scores.items(), key=lambda kv: kv[1], reverse=True)[:20]
    if top_betweenness:
        fig, ax = plt.subplots(figsize=(10, 6))
        labels_bc = [nid.replace("editor:", "") for nid, _ in top_betweenness]
        values_bc = [v for _, v in top_betweenness]
        ax.barh(labels_bc[::-1], values_bc[::-1])
        ax.set_xlabel("Betweenness Centrality")
        ax.set_title("Top 20 Editors by Betweenness Centrality")
        plt.tight_layout()
        fig.savefig(OUT / "betweenness_centrality.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        print("  -> betweenness_centrality.png")

    # 3. Community sizes
    communities = detect_communities(G)
    if communities:
        largest = sorted(communities, key=len, reverse=True)[:5]
        fig, ax = plt.subplots(figsize=(8, 5))
        sizes = [len(c) for c in largest]
        labels_comm = [f"Community {i + 1}" for i in range(len(largest))]
        ax.bar(labels_comm, sizes)
        ax.set_ylabel("Number of Editors")
        ax.set_title("Top 5 Largest Editor Communities")
        plt.tight_layout()
        fig.savefig(OUT / "community_sizes.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        print("  -> community_sizes.png")

    # 4. Serial disputants
    serial = serial_disputants(G, min_cases=2)
    if serial:
        case_counts = [count for _, count, _ in serial]
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.hist(case_counts, bins=range(2, max(case_counts) + 2), edgecolor="white")
        ax.set_xlabel("Number of Cases")
        ax.set_ylabel("Number of Editors")
        ax.set_title("Distribution of Cross-Case Editor Appearances")
        plt.tight_layout()
        fig.savefig(OUT / "serial_disputants.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        print("  -> serial_disputants.png")

    # 5. Article-case bipartite
    B = article_case_bipartite(G)
    articles = [n for n, d in B.nodes(data=True) if d.get("node_type") == "article"]
    if articles:
        art_degree = sorted(
            [(n, B.degree(n)) for n in articles], key=lambda x: x[1], reverse=True
        )[:20]
        fig, ax = plt.subplots(figsize=(10, 6))
        labels_art = [nid.replace("article:", "")[:40] for nid, _ in art_degree]
        values_art = [v for _, v in art_degree]
        ax.barh(labels_art[::-1], values_art[::-1])
        ax.set_xlabel("Number of Arbitration Cases")
        ax.set_title("Top 20 Most-Disputed Articles")
        plt.tight_layout()
        fig.savefig(OUT / "article_case_bipartite.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        print("  -> article_case_bipartite.png")

    # 6. Escalation features
    import pandas as pd

    rows = []
    for case in cases:
        case_g = build_case_graph(case)
        s = graph_summary(case_g)
        rows.append(
            {
                "editors": s["node_types"].get("editor", 0),
                "reverts": s["edge_types"].get("REVERTS", 0),
                "duration_days": case.case_duration_days,
                "conflict_density": (
                    s["edge_types"].get("REVERTS", 0)
                    / max(s["node_types"].get("editor", 1), 1)
                ),
            }
        )
    if rows:
        df = pd.DataFrame(rows)
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        axes[0].scatter(df["editors"], df["reverts"], alpha=0.5, s=20)
        axes[0].set_xlabel("Number of Editors")
        axes[0].set_ylabel("Revert Edges")
        axes[0].set_title("Editors vs. Conflict Edges per Case")
        axes[1].scatter(df["duration_days"], df["conflict_density"], alpha=0.5, s=20)
        axes[1].set_xlabel("Case Duration (days)")
        axes[1].set_ylabel("Conflict Density (reverts/editor)")
        axes[1].set_title("Duration vs. Conflict Density")
        plt.tight_layout()
        fig.savefig(OUT / "escalation_features.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        print("  -> escalation_features.png")

    # 7. Conflict network
    if conflict_g.number_of_nodes() > 0:
        community_map = {}
        if communities:
            for idx, comm in enumerate(communities):
                for node in comm:
                    community_map[node] = idx

        # Use full graph or largest CC if too big
        if conflict_g.number_of_nodes() < 500:
            draw_g = conflict_g.to_undirected()
            title = "Editor Conflict Network (colored by community)"
        else:
            ug = conflict_g.to_undirected()
            largest_cc = max(nx.connected_components(ug), key=len)
            draw_g = ug.subgraph(largest_cc)
            title = f"Largest Connected Component ({draw_g.number_of_nodes()} editors)"

        pos = nx.spring_layout(draw_g, seed=42, k=1.5)
        degrees = dict(draw_g.degree(weight="weight"))
        max_deg = max(degrees.values()) if degrees else 1
        node_sizes = [100 + 400 * (degrees.get(n, 0) / max_deg) for n in draw_g.nodes()]
        node_colors = [community_map.get(n, 0) for n in draw_g.nodes()]

        fig, ax = plt.subplots(figsize=(14, 10))
        nx.draw_networkx(
            draw_g,
            pos,
            ax=ax,
            node_size=node_sizes,
            node_color=node_colors,
            cmap=plt.cm.Set3,
            with_labels=False,
            edge_color="#cccccc",
            alpha=0.8,
            width=0.5,
        )
        ax.set_title(title)
        ax.axis("off")
        plt.tight_layout()
        fig.savefig(OUT / "conflict_network.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        print("  -> conflict_network.png")

    print(f"\nAll figures saved to {OUT}")


if __name__ == "__main__":
    main()
