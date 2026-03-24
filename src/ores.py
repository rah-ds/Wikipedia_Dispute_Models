"""ORES/Lift Wing ML scoring client for Wikipedia revisions.

ORES (Objective Revision Evaluation Service) provides pre-computed ML predictions
for Wikipedia revisions. Lift Wing is the newer API that replaced ORES.

Provides:
- damaging: probability an edit harms quality (0-1)
- goodfaith: probability an edit was well-intentioned (0-1)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Lift Wing API endpoints
LIFT_WING_BASE_URL = "https://api.wikimedia.org/service/lw/inference/v1/models"

# Model names for English Wikipedia
ENWIKI_DAMAGING_MODEL = "enwiki-damaging"
ENWIKI_GOODFAITH_MODEL = "enwiki-goodfaith"

# Legacy ORES endpoint (still works for some wikis)
ORES_BASE_URL = "https://ores.wikimedia.org/v3/scores"


@dataclass
class OresScore:
    """ML scores for a single revision."""

    revid: int
    damaging: float | None = None
    goodfaith: float | None = None
    damaging_prediction: bool | None = None
    goodfaith_prediction: bool | None = None
    error: str | None = None


class OresClient:
    """
    Client for ORES/Lift Wing scoring API.

    Note: The ORES service was migrated to Lift Wing. This client
    supports both APIs for compatibility.
    """

    def __init__(
        self,
        wiki: str = "enwiki",
        use_lift_wing: bool = True,
        user_agent: str = "WikipediaDisputeModels/1.0",
        rate_limit: float = 10.0,  # requests per second
    ):
        """
        Initialize ORES client.

        Args:
            wiki: Wiki database name (e.g., "enwiki", "dewiki")
            use_lift_wing: Use Lift Wing API (default) or legacy ORES
            user_agent: User agent for API requests
            rate_limit: Max requests per second
        """
        self.wiki = wiki
        self.use_lift_wing = use_lift_wing
        self.user_agent = user_agent
        self.min_delay = 1.0 / rate_limit
        self._last_request = 0.0

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "application/json",
            }
        )

    def _throttle(self) -> None:
        """Apply rate limiting."""
        elapsed = time.time() - self._last_request
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        self._last_request = time.time()

    def get_score(self, revid: int) -> OresScore:
        """
        Get ML scores for a single revision.

        Args:
            revid: Revision ID

        Returns:
            OresScore with damaging and goodfaith scores
        """
        scores = self.get_scores([revid])
        return scores.get(revid, OresScore(revid=revid, error="No score returned"))

    def get_scores(
        self,
        revids: list[int],
        models: list[str] | None = None,
    ) -> dict[int, OresScore]:
        """
        Get ML scores for multiple revisions.

        Args:
            revids: List of revision IDs (max 50 per request)
            models: Models to query (default: damaging, goodfaith)

        Returns:
            Dictionary mapping revid to OresScore
        """
        if not revids:
            return {}

        if models is None:
            models = ["damaging", "goodfaith"]

        results = {}

        # Process in batches of 50
        for i in range(0, len(revids), 50):
            batch = revids[i : i + 50]

            if self.use_lift_wing:
                batch_results = self._fetch_lift_wing(batch, models)
            else:
                batch_results = self._fetch_ores(batch, models)

            results.update(batch_results)

        return results

    def _fetch_lift_wing(
        self,
        revids: list[int],
        models: list[str],
    ) -> dict[int, OresScore]:
        """Fetch scores from Lift Wing API."""
        results = {}

        for revid in revids:
            score = OresScore(revid=revid)

            for model in models:
                model_name = f"{self.wiki}-{model}"
                url = f"{LIFT_WING_BASE_URL}/{model_name}:predict"

                self._throttle()

                try:
                    response = self.session.post(
                        url,
                        json={"rev_id": revid},
                        timeout=30,
                    )
                    response.raise_for_status()
                    data = response.json()

                    # Parse Lift Wing response
                    output = data.get("output", {})
                    probabilities = output.get("probabilities", {})

                    if model == "damaging":
                        score.damaging = probabilities.get(
                            "true", probabilities.get("True")
                        )
                        score.damaging_prediction = output.get("prediction") == "true"
                    elif model == "goodfaith":
                        score.goodfaith = probabilities.get(
                            "true", probabilities.get("True")
                        )
                        score.goodfaith_prediction = output.get("prediction") == "true"

                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 404:
                        score.error = f"Revision {revid} not found or model unavailable"
                    else:
                        score.error = str(e)
                    logger.warning(f"Lift Wing error for {revid}: {e}")
                except Exception as e:
                    score.error = str(e)
                    logger.error(f"Lift Wing request failed for {revid}: {e}")

            results[revid] = score

        return results

    def _fetch_ores(
        self,
        revids: list[int],
        models: list[str],
    ) -> dict[int, OresScore]:
        """Fetch scores from legacy ORES API."""
        results = {}

        # ORES can batch revisions
        revid_str = "|".join(str(r) for r in revids)
        models_str = "|".join(models)
        url = f"{ORES_BASE_URL}/{self.wiki}/?models={models_str}&revids={revid_str}"

        self._throttle()

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            wiki_data = data.get(self.wiki, {}).get("scores", {})

            for revid in revids:
                revid_str = str(revid)
                score = OresScore(revid=revid)

                if revid_str not in wiki_data:
                    score.error = "Revision not scored"
                    results[revid] = score
                    continue

                rev_scores = wiki_data[revid_str]

                if "damaging" in rev_scores and "error" not in rev_scores["damaging"]:
                    prob = rev_scores["damaging"]["score"]["probability"]
                    score.damaging = prob.get("true", prob.get("True"))
                    score.damaging_prediction = rev_scores["damaging"]["score"][
                        "prediction"
                    ]

                if "goodfaith" in rev_scores and "error" not in rev_scores["goodfaith"]:
                    prob = rev_scores["goodfaith"]["score"]["probability"]
                    score.goodfaith = prob.get("true", prob.get("True"))
                    score.goodfaith_prediction = rev_scores["goodfaith"]["score"][
                        "prediction"
                    ]

                results[revid] = score

        except Exception as e:
            logger.error(f"ORES request failed: {e}")
            for revid in revids:
                results[revid] = OresScore(revid=revid, error=str(e))

        return results

    def score_revisions(
        self,
        revisions: list[dict[str, Any]],
        revid_key: str = "revid",
    ) -> list[dict[str, Any]]:
        """
        Add ORES scores to a list of revision dictionaries.

        Args:
            revisions: List of revision dicts
            revid_key: Key containing revision ID

        Returns:
            Revisions with added ores_damaging and ores_goodfaith fields
        """
        revids = [r[revid_key] for r in revisions if revid_key in r]
        scores = self.get_scores(revids)

        for rev in revisions:
            revid = rev.get(revid_key)
            if revid and revid in scores:
                score = scores[revid]
                rev["ores_damaging"] = score.damaging
                rev["ores_goodfaith"] = score.goodfaith
                rev["ores_damaging_prediction"] = score.damaging_prediction
                rev["ores_goodfaith_prediction"] = score.goodfaith_prediction

        return revisions


def get_revision_quality(revids: list[int], wiki: str = "enwiki") -> dict[int, dict]:
    """
    Convenience function to get quality scores for revisions.

    Args:
        revids: List of revision IDs
        wiki: Wiki database name

    Returns:
        Dictionary mapping revid to quality metrics
    """
    client = OresClient(wiki=wiki)
    scores = client.get_scores(revids)

    return {
        revid: {
            "damaging": score.damaging,
            "goodfaith": score.goodfaith,
            "likely_bad_faith": (score.goodfaith is not None and score.goodfaith < 0.5),
            "likely_damaging": (score.damaging is not None and score.damaging > 0.5),
        }
        for revid, score in scores.items()
    }
