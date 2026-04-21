"""Smoke tests for the pipeline filter and aggregation.

These don't hit the network — they verify the scoring/filter logic.
Run with: `pytest -q`.
"""

from __future__ import annotations

from src.pipeline import (
    DIMENSIONS,
    aggregate_scores,
    analyze_turn,
    format_flags_for_prompt,
)


SLOP = ["it is important to note", "in conclusion", "delve into"]


def test_analyze_turn_counts_citations_and_slop():
    text = (
        "It is important to note that broadband access [S1] is critical. "
        "In conclusion, we delve into [S2] the failure modes. "
        "Also [S1] supports this."
    )
    f = analyze_turn(
        text,
        debater_id="D1",
        round_name="opening",
        min_citations=2,
        slop_phrases=SLOP,
        slop_warn_threshold_per_1k=3.0,
    )
    assert f.citation_count == 3
    assert f.unique_citations == 2
    assert len(f.slop_hits) == 3
    assert f.slop_rate_per_1k > 0
    # With 3 citations we should not warn about min_citations.
    assert not any("Low citation" in w for w in f.warnings)


def test_analyze_turn_flags_low_citations():
    text = "A bare claim with no sources at all."
    f = analyze_turn(
        text,
        debater_id="D1",
        round_name="opening",
        min_citations=2,
        slop_phrases=SLOP,
        slop_warn_threshold_per_1k=3.0,
    )
    assert f.citation_count == 0
    assert any("Low citation" in w for w in f.warnings)


def test_aggregate_scores_ranks_and_detects_outliers():
    def card(jid, scores):
        return {
            "judge_id": jid,
            "judge_name": jid,
            "scores": {
                "D1": {dim: {"score": scores[0][i], "quote": "q", "note": "n"} for i, dim in enumerate(DIMENSIONS)},
                "D2": {dim: {"score": scores[1][i], "quote": "q", "note": "n"} for i, dim in enumerate(DIMENSIONS)},
            },
        }

    cards = [
        card("J1", [[8, 8, 7, 8, 8], [5, 5, 4, 6, 5]]),
        card("J2", [[8, 7, 7, 7, 8], [5, 4, 4, 5, 5]]),
        # J3 is an outlier: scores D1 very low.
        card("J3", [[2, 2, 2, 2, 2], [5, 5, 5, 5, 5]]),
    ]

    agg = aggregate_scores(cards, ["D1", "D2"], outlier_z=1.2)
    # J3's D1 scores should appear in outliers for at least one dimension.
    assert any(o["judge_id"] == "J3" and o["debater_id"] == "D1" for o in agg["outliers"])
    # Ranking still exists.
    assert agg["ranking"][0] in ("D1", "D2")
    assert agg["winner"] in ("D1", "D2")


def test_format_flags_for_prompt_is_stable():
    text = "No citations here."
    f = analyze_turn(
        text,
        debater_id="D1",
        round_name="opening",
        min_citations=2,
        slop_phrases=SLOP,
        slop_warn_threshold_per_1k=3.0,
    )
    s = format_flags_for_prompt([f])
    assert "D1" in s and "opening" in s and "Low citation" in s
