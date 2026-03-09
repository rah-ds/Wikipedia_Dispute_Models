#!/usr/bin/env python3
"""
Count records in Wikipedia dispute resolution JSON files and produce a bar chart.

Usage:
    python wiki_counts.py <arbitration.json> <drn.json> <rfcs.json>

Example:
    python wiki_counts.py arbitration_cases.json drn_cases.json rfcs.json
"""

import sys
import json
import matplotlib.pyplot as plt


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    if len(sys.argv) != 4:
        print(__doc__.strip())
        sys.exit(1)

    arb_path, drn_path, rfc_path = sys.argv[1], sys.argv[2], sys.argv[3]

    arb_data = load_json(arb_path)
    drn_data = load_json(drn_path)
    rfc_data = load_json(rfc_path)

    # --- Count records ---
    arb_count = len(arb_data) if isinstance(arb_data, list) else 0
    drn_count = len(drn_data.get("revisions", [])) if isinstance(drn_data, dict) else 0
    rfc_count = (
        rfc_data.get("total_rfcs", len(rfc_data.get("rfcs", [])))
        if isinstance(rfc_data, dict)
        else 0
    )

    print(f"{'Type':<25} {'Count':>8}")
    print("-" * 35)
    print(f"{'Arbitration Cases':<25} {arb_count:>8}")
    print(f"{'DRN Revisions':<25} {drn_count:>8}")
    print(f"{'RFCs':<25} {rfc_count:>8}")

    # --- Bar chart ---
    labels = ["Arbitration\nCases", "DRN\nRevisions", "RFCs"]
    counts = [arb_count, drn_count, rfc_count]
    colors = ["#4C72B0", "#DD8452", "#55A868"]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(labels, counts, color=colors, width=0.5, edgecolor="white")

    for bar, c in zip(bars, counts):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(counts) * 0.02,
            str(c),
            ha="center",
            va="bottom",
            fontweight="bold",
            fontsize=13,
        )

    ax.set_ylabel("Number of Records")
    ax.set_title("Wikipedia Dispute Resolution — Record Counts by Type")
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()

    out = "dispute_resolution_counts.png"
    plt.savefig(out, dpi=150)
    print(f"\nChart saved to {out}")
    plt.show()


if __name__ == "__main__":
    main()
