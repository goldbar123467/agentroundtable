"""Standard pipeline filter + scoring aggregation.

Two jobs:
  1. `analyze_turn` — annotate a single debater turn with quality flags
     (citation density, slop-phrase hits). Attached to judge prompts so
     judges see the same flags.
  2. `aggregate_scores` — combine judge scorecards into a verdict. Computes
     mean, median, and per-dimension z-scores to flag outlier judges.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import Any

CITATION_RE = re.compile(r"\[S(\d+)\]")
WORD_RE = re.compile(r"\b\w+\b")


@dataclass
class TurnFlags:
    debater_id: str
    round_name: str
    citation_count: int
    unique_citations: int
    word_count: int
    slop_hits: list[str] = field(default_factory=list)
    slop_rate_per_1k: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "debater_id": self.debater_id,
            "round": self.round_name,
            "citation_count": self.citation_count,
            "unique_citations": self.unique_citations,
            "word_count": self.word_count,
            "slop_hits": self.slop_hits,
            "slop_rate_per_1k": round(self.slop_rate_per_1k, 2),
            "warnings": self.warnings,
        }


def analyze_turn(
    text: str,
    debater_id: str,
    round_name: str,
    *,
    min_citations: int,
    slop_phrases: list[str],
    slop_warn_threshold_per_1k: float,
) -> TurnFlags:
    cites = CITATION_RE.findall(text)
    unique = sorted(set(cites), key=int)
    words = WORD_RE.findall(text)
    wc = len(words)

    lower = text.lower()
    hits: list[str] = []
    for phrase in slop_phrases:
        n = lower.count(phrase.lower())
        hits.extend([phrase] * n)

    rate = (len(hits) / wc * 1000) if wc else 0.0

    flags = TurnFlags(
        debater_id=debater_id,
        round_name=round_name,
        citation_count=len(cites),
        unique_citations=len(unique),
        word_count=wc,
        slop_hits=hits,
        slop_rate_per_1k=rate,
    )
    if round_name in ("opening", "rebuttal") and len(cites) < min_citations:
        flags.warnings.append(
            f"Low citation count: {len(cites)} (< min {min_citations})"
        )
    if rate > slop_warn_threshold_per_1k:
        flags.warnings.append(
            f"High slop rate: {rate:.2f}/1k words (> {slop_warn_threshold_per_1k})"
        )
    return flags


def format_flags_for_prompt(flags: list[TurnFlags]) -> str:
    if not flags:
        return "(no flags)"
    lines = []
    for f in flags:
        tag = " ⚠" if f.warnings else ""
        lines.append(
            f"- {f.debater_id} / {f.round_name}: "
            f"{f.citation_count} citations ({f.unique_citations} unique), "
            f"{f.word_count} words, "
            f"slop={f.slop_rate_per_1k:.2f}/1k{tag}"
        )
        for w in f.warnings:
            lines.append(f"    · {w}")
    return "\n".join(lines)


DIMENSIONS = ("logic", "evidence", "rebuttal", "originality", "position_fit")


def aggregate_scores(
    scorecards: list[dict[str, Any]],
    debater_ids: list[str],
    *,
    outlier_z: float,
) -> dict[str, Any]:
    """Return a dict with per-debater totals and outlier judge flags."""
    per_debater: dict[str, dict[str, Any]] = {d: {"dimensions": {}} for d in debater_ids}

    for d in debater_ids:
        dim_totals: list[float] = []
        for dim in DIMENSIONS:
            raw = []
            for card in scorecards:
                try:
                    raw.append(int(card["scores"][d][dim]["score"]))
                except (KeyError, TypeError, ValueError):
                    continue
            if raw:
                per_debater[d]["dimensions"][dim] = {
                    "raw": raw,
                    "mean": round(statistics.mean(raw), 2),
                    "median": statistics.median(raw),
                }
                dim_totals.append(statistics.mean(raw))
            else:
                per_debater[d]["dimensions"][dim] = {"raw": [], "mean": None, "median": None}
        per_debater[d]["total"] = round(sum(dim_totals), 2) if dim_totals else None

    # Outlier judge detection: per judge, per debater, per dimension z-score.
    outliers: list[dict[str, Any]] = []
    for j_idx, card in enumerate(scorecards):
        judge_id = card.get("judge_id", f"J{j_idx+1}")
        for d in debater_ids:
            for dim in DIMENSIONS:
                raw = per_debater[d]["dimensions"][dim]["raw"]
                if len(raw) < 3:
                    continue
                mu = statistics.mean(raw)
                sigma = statistics.pstdev(raw) or 1e-9
                try:
                    val = int(card["scores"][d][dim]["score"])
                except (KeyError, TypeError, ValueError):
                    continue
                z = (val - mu) / sigma
                if abs(z) >= outlier_z:
                    outliers.append(
                        {
                            "judge_id": judge_id,
                            "debater_id": d,
                            "dimension": dim,
                            "score": val,
                            "mean": round(mu, 2),
                            "z": round(z, 2),
                        }
                    )

    ranking = sorted(
        (d for d in debater_ids if per_debater[d]["total"] is not None),
        key=lambda d: per_debater[d]["total"],
        reverse=True,
    )

    return {
        "per_debater": per_debater,
        "ranking": ranking,
        "winner": ranking[0] if ranking else None,
        "outliers": outliers,
    }
