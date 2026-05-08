"""
Extract and fetch evidence diffs cited in ArbCom evidence pages.

ArbCom evidence pages contain references to specific article edits using
``[[Special:Diff/REVID]]`` or ``[[Special:Diff/OLDREVID/NEWREVID]]`` patterns.
These diffs are the actual edits that triggered or exemplify the dispute —
the most direct signal of what brought a case to arbitration.

Usage example::

    from src.wiki import WikiClient
    from src.evidence import extract_diff_refs, fetch_evidence_diffs

    client = WikiClient()
    page = client.get_page("Wikipedia:Arbitration/Requests/Case/Gamergate/Evidence")
    refs = extract_diff_refs(page.text)
    diffs = fetch_evidence_diffs(client, refs, max_diffs=30)
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns for diff references in wikitext
# ---------------------------------------------------------------------------

# [[Special:Diff/OLD/NEW]] — explicit before/after pair
_DIFF_PAIR_RE = re.compile(
    r"\[\[Special:Diff/(\d+)/(\d+)(?:[|\]][^\]]*)?(?:\]\])?",
    re.IGNORECASE,
)

# [[Special:Diff/REVID]] — single revision (compare against its parent)
# Must not be followed immediately by /\d+ (already captured by pair pattern)
_DIFF_SINGLE_RE = re.compile(
    r"\[\[Special:Diff/(\d+)(?!/\d)(?:[|\]][^\]]*)?(?:\]\])?",
    re.IGNORECASE,
)

# External links: https://en.wikipedia.org/w/index.php?...&diff=XXXX&oldid=YYYY
_EXT_DIFF_RE = re.compile(
    r"diff=(\d+)&(?:amp;)?oldid=(\d+)|oldid=(\d+)&(?:amp;)?diff=(\d+)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_diff_refs(wikitext: str) -> list[dict]:
    """
    Extract diff references from evidence page wikitext.

    Finds three reference styles:
    - ``[[Special:Diff/OLD/NEW]]`` — explicit rev pair
    - ``[[Special:Diff/REVID]]`` — single revision vs its parent
    - External ``diff=X&oldid=Y`` URLs

    Args:
        wikitext: Raw wikitext of an evidence page.

    Returns:
        List of dicts with keys ``from_rev`` (int or None), ``to_rev`` (int),
        and ``raw`` (matched text).  Deduplicated by (from_rev, to_rev).
    """
    refs: list[dict] = []
    seen: set[tuple[int | None, int]] = set()

    # Paired diffs first (most specific pattern)
    for m in _DIFF_PAIR_RE.finditer(wikitext):
        from_rev = int(m.group(1))
        to_rev = int(m.group(2))
        key: tuple[int | None, int] = (from_rev, to_rev)
        if key not in seen:
            seen.add(key)
            refs.append({"from_rev": from_rev, "to_rev": to_rev, "raw": m.group(0)})

    # Single revision diffs
    for m in _DIFF_SINGLE_RE.finditer(wikitext):
        rev = int(m.group(1))
        key = (None, rev)
        if key not in seen:
            seen.add(key)
            refs.append({"from_rev": None, "to_rev": rev, "raw": m.group(0)})

    # External URL diffs (diff=X&oldid=Y)
    for m in _EXT_DIFF_RE.finditer(wikitext):
        if m.group(1) and m.group(2):
            to_rev, from_rev = int(m.group(1)), int(m.group(2))
        else:
            from_rev, to_rev = int(m.group(3)), int(m.group(4))
        key = (from_rev, to_rev)
        if key not in seen:
            seen.add(key)
            refs.append({"from_rev": from_rev, "to_rev": to_rev, "raw": m.group(0)})

    logger.debug("Extracted %d diff refs from evidence wikitext", len(refs))
    return refs


def fetch_evidence_diffs(
    client,
    diff_refs: list[dict],
    max_diffs: int = 50,
    delay: float = 0.3,
) -> list[dict]:
    """
    Fetch diff content for a list of diff references.

    For paired refs (from_rev + to_rev) uses ``client.compare_revisions()``.
    For single-revision refs (from_rev=None) first fetches the revision to
    get its parent ID, then compares parent → revision.

    Args:
        client: WikiClient instance.
        diff_refs: List of dicts from :func:`extract_diff_refs`.
        max_diffs: Cap on number of diffs to fetch (API-intensive).
        delay: Seconds to sleep between requests.

    Returns:
        List of diff dicts.  Each dict contains at minimum ``from_revid``,
        ``to_revid``, ``diff_html``, and ``ref_type``.  On error the dict
        contains ``error`` instead of diff content.
    """
    import time

    results: list[dict] = []

    for ref in diff_refs[:max_diffs]:
        from_rev: int | None = ref.get("from_rev")
        to_rev: int | None = ref.get("to_rev")

        try:
            if from_rev is not None and to_rev is not None:
                diff = client.compare_revisions(from_rev, to_rev)
                diff["ref_type"] = "pair"
                diff["raw_ref"] = ref.get("raw", "")
                results.append(diff)

            elif to_rev is not None:
                # Fetch parent from the revision record
                rev_info = client.get_revision_content(to_rev)
                if rev_info is None:
                    results.append(
                        {
                            "to_rev": to_rev,
                            "ref_type": "single",
                            "raw_ref": ref.get("raw", ""),
                            "error": "revision not found",
                        }
                    )
                    continue

                parent_id: int = rev_info.get("parentid") or 0
                if parent_id:
                    diff = client.compare_revisions(parent_id, to_rev)
                    diff["ref_type"] = "single"
                    diff["raw_ref"] = ref.get("raw", "")
                    results.append(diff)
                else:
                    # First revision of a page — no parent to compare
                    results.append(
                        {
                            "to_revid": to_rev,
                            "ref_type": "single_first_rev",
                            "raw_ref": ref.get("raw", ""),
                            "user": rev_info.get("user"),
                            "timestamp": rev_info.get("timestamp"),
                            "comment": rev_info.get("comment", ""),
                            "size": rev_info.get("size"),
                        }
                    )

        except Exception as exc:
            logger.warning("Failed to fetch diff %s→%s: %s", from_rev, to_rev, exc)
            results.append(
                {
                    "from_rev": from_rev,
                    "to_rev": to_rev,
                    "ref_type": "error",
                    "raw_ref": ref.get("raw", ""),
                    "error": str(exc),
                }
            )

        time.sleep(delay)

    return results
