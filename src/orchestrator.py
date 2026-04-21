"""Debate orchestrator.

Flow:
  1. Load config, roles, skills.
  2. Build 4 debaters and 3 judges from config.
  3. Parallel research phase (Brave + per-debater research memo).
  4. Sequential rounds (opening → rebuttal → closing). Within a round,
     each debater sees the transcript assembled so far *from prior rounds*
     plus turns earlier in the current round, so later debaters can react
     to earlier ones (this is deliberate — roundtables aren't simultaneous).
  5. Pipeline filter annotates every turn.
  6. Parallel judging phase.
  7. Aggregate scores, write artifacts.

Artifacts written to `transcripts/<slug>/`:
  - transcript.md   — human-readable
  - transcript.json — full structured run
  - scorecard.json  — aggregated scores + outliers
  - dossiers.json   — raw Brave results per debater
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from .debater import Debater
from .judge import Judge
from .pipeline import (
    DIMENSIONS,
    TurnFlags,
    aggregate_scores,
    analyze_turn,
    format_flags_for_prompt,
)

ROOT = Path(__file__).resolve().parent.parent
ROLES_DIR = ROOT / "roles"
TRANSCRIPTS_DIR = ROOT / "transcripts"


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:60] or "debate"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _word_budget(max_tokens: int) -> int:
    # Words ≈ tokens * 0.75 — give the model a target ~85% of the ceiling.
    return int(max_tokens * 0.75 * 0.85)


class Orchestrator:
    def __init__(self, config_path: Path):
        self.config = yaml.safe_load(_read(config_path))
        self.debater_role = _read(ROLES_DIR / "debater" / "role.md")
        self.debater_prompts = _read(ROLES_DIR / "debater" / "prompts.md")
        self.judge_role = _read(ROLES_DIR / "judge" / "role.md")
        self.judge_prompts = _read(ROLES_DIR / "judge" / "prompts.md")

    # --- construction ------------------------------------------------------

    def build_debaters(self, positions: dict[str, str]) -> list[Debater]:
        cfg = self.config
        out = []
        for d in cfg["debaters"]:
            pos = positions.get(d["id"])
            if not pos:
                raise ValueError(f"No position assigned to debater {d['id']}")
            out.append(
                Debater(
                    id=d["id"],
                    name=d["name"],
                    model=d["model"],
                    position=pos,
                    role_md=self.debater_role,
                    prompts_md=self.debater_prompts,
                    temperature=cfg["debate"]["temperature_debater"],
                    max_tokens=cfg["debate"]["max_tokens_per_turn"],
                )
            )
        return out

    def build_judges(self) -> list[Judge]:
        cfg = self.config
        judge_max_tokens = cfg["debate"].get("max_tokens_per_judge", 2400)
        return [
            Judge(
                id=j["id"],
                name=j["name"],
                model=j["model"],
                role_md=self.judge_role,
                prompts_md=self.judge_prompts,
                temperature=cfg["debate"]["temperature_judge"],
                max_tokens=judge_max_tokens,
            )
            for j in cfg["judges"]
        ]

    # --- phases ------------------------------------------------------------

    def research_phase(self, debaters: list[Debater], topic: str) -> None:
        n = self.config["debate"]["research_results_per_debater"]
        with ThreadPoolExecutor(max_workers=len(debaters)) as ex:
            futures = {
                ex.submit(d.run_research, topic, results_count=n): d for d in debaters
            }
            for fut in as_completed(futures):
                d = futures[fut]
                fut.result()  # raise on failure
                print(f"  [research] {d.id} {d.name}: {len(d.dossier_entries)} results")

    def round_phase(
        self,
        debaters: list[Debater],
        topic: str,
        phase: str,
        transcript_blocks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Run one round across all debaters sequentially (later debaters see
        earlier turns in the same round). Returns new transcript blocks.
        """
        pipe = self.config["pipeline"]
        max_tokens = self.config["debate"]["max_tokens_per_turn"]
        budget = _word_budget(max_tokens)

        new_blocks: list[dict[str, Any]] = []
        for d in debaters:
            others = ", ".join(
                f"{x.name} ({x.position})" for x in debaters if x.id != d.id
            )
            transcript_text = _render_transcript(transcript_blocks + new_blocks)
            text = d.speak(
                phase,
                topic=topic,
                transcript=transcript_text or "(this is the first turn)",
                other_debaters=others,
                word_budget=budget,
            )
            flags = analyze_turn(
                text,
                debater_id=d.id,
                round_name=phase,
                min_citations=pipe["min_citations_per_argument"],
                slop_phrases=pipe["slop_phrases"],
                slop_warn_threshold_per_1k=pipe["slop_warn_threshold_per_1k"],
            )
            new_blocks.append(
                {
                    "debater_id": d.id,
                    "debater_name": d.name,
                    "position": d.position,
                    "phase": phase,
                    "text": text,
                    "flags": flags.to_dict(),
                }
            )
            tag = " ⚠" if flags.warnings else ""
            print(
                f"  [{phase}] {d.id} {d.name}: "
                f"{flags.word_count}w, {flags.citation_count} cites{tag}"
            )
        return new_blocks

    def judge_phase(
        self,
        debaters: list[Debater],
        judges: list[Judge],
        topic: str,
        transcript_blocks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        debaters_and_positions = "\n".join(
            f"- {d.id} {d.name}: {d.position}" for d in debaters
        )
        transcript_text = _render_transcript(transcript_blocks)
        all_flags: list[TurnFlags] = [
            _flags_from_dict(b["flags"]) for b in transcript_blocks
        ]
        pipeline_flags = format_flags_for_prompt(all_flags)
        dossiers = _render_dossiers(debaters)

        cards: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=len(judges)) as ex:
            futures = {
                ex.submit(
                    j.score,
                    topic=topic,
                    debaters_and_positions=debaters_and_positions,
                    transcript=transcript_text,
                    pipeline_flags=pipeline_flags,
                    dossiers=dossiers,
                ): j
                for j in judges
            }
            for fut in as_completed(futures):
                j = futures[fut]
                card = fut.result()
                card.setdefault("judge_id", j.id)
                card.setdefault("judge_name", j.name)
                cards.append(card)
                err = " (parse error)" if card.get("parse_error") else ""
                print(f"  [judge] {j.id} {j.name}: scorecard received{err}")
        return cards

    # --- top-level ---------------------------------------------------------

    def run(self, topic: str, positions: dict[str, str]) -> Path:
        t0 = time.time()
        debaters = self.build_debaters(positions)
        judges = self.build_judges()

        print(f"\n=== agentroundtable: {topic} ===")
        print("Debaters:")
        for d in debaters:
            print(f"  {d.id} {d.name} [{d.model}]  → {d.position}")
        print("Judges:")
        for j in judges:
            print(f"  {j.id} {j.name} [{j.model}]")

        print("\n--- research ---")
        self.research_phase(debaters, topic)

        blocks: list[dict[str, Any]] = []
        for phase in self.config["debate"]["rounds"]:
            print(f"\n--- {phase} ---")
            blocks.extend(self.round_phase(debaters, topic, phase, blocks))

        print("\n--- judging ---")
        cards = self.judge_phase(debaters, judges, topic, blocks)

        agg = aggregate_scores(
            cards,
            [d.id for d in debaters],
            outlier_z=self.config["pipeline"]["outlier_z"],
        )

        out_dir = TRANSCRIPTS_DIR / f"{int(time.time())}-{_slugify(topic)}"
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_artifacts(out_dir, topic, debaters, judges, blocks, cards, agg)

        print(f"\n=== done in {time.time() - t0:.1f}s ===")
        print(f"Ranking: {' > '.join(agg['ranking']) or '(none)'}")
        print(f"Winner: {agg['winner']}")
        print(f"Artifacts: {out_dir}")
        return out_dir


# --- helpers -------------------------------------------------------------


def _render_transcript(blocks: list[dict[str, Any]]) -> str:
    if not blocks:
        return ""
    out = []
    for b in blocks:
        out.append(
            f"### {b['phase'].upper()} — {b['debater_id']} {b['debater_name']} "
            f"({b['position']})\n{b['text']}"
        )
    return "\n\n".join(out)


def _render_dossiers(debaters: list[Debater]) -> str:
    out = []
    for d in debaters:
        out.append(f"### {d.id} {d.name} ({d.position}) dossier")
        out.append(d.dossier_text or "(empty)")
    return "\n\n".join(out)


def _flags_from_dict(d: dict[str, Any]) -> TurnFlags:
    return TurnFlags(
        debater_id=d["debater_id"],
        round_name=d["round"],
        citation_count=d["citation_count"],
        unique_citations=d["unique_citations"],
        word_count=d["word_count"],
        slop_hits=list(d.get("slop_hits") or []),
        slop_rate_per_1k=float(d.get("slop_rate_per_1k") or 0.0),
        warnings=list(d.get("warnings") or []),
    )


def _write_artifacts(
    out_dir: Path,
    topic: str,
    debaters: list[Debater],
    judges: list[Judge],
    blocks: list[dict[str, Any]],
    cards: list[dict[str, Any]],
    agg: dict[str, Any],
) -> None:
    # dossiers.json
    (out_dir / "dossiers.json").write_text(
        json.dumps(
            {d.id: {"name": d.name, "position": d.position, "entries": d.dossier_entries, "memo": d.research_memo} for d in debaters},
            indent=2,
        ),
        encoding="utf-8",
    )

    # transcript.json
    (out_dir / "transcript.json").write_text(
        json.dumps(
            {
                "topic": topic,
                "debaters": [
                    {"id": d.id, "name": d.name, "model": d.model, "position": d.position}
                    for d in debaters
                ],
                "judges": [
                    {"id": j.id, "name": j.name, "model": j.model} for j in judges
                ],
                "blocks": blocks,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # scorecard.json
    (out_dir / "scorecard.json").write_text(
        json.dumps({"cards": cards, "aggregate": agg}, indent=2),
        encoding="utf-8",
    )

    # transcript.md
    md = [f"# {topic}\n"]
    md.append("## Debaters\n")
    for d in debaters:
        md.append(f"- **{d.id} {d.name}** [{d.model}] → {d.position}")
    md.append("\n## Judges\n")
    for j in judges:
        md.append(f"- **{j.id} {j.name}** [{j.model}]")
    md.append("\n## Transcript\n")
    for b in blocks:
        md.append(
            f"### {b['phase'].upper()} — {b['debater_id']} {b['debater_name']} ({b['position']})"
        )
        md.append(b["text"])
        if b["flags"]["warnings"]:
            md.append(f"\n> _pipeline flags:_ {', '.join(b['flags']['warnings'])}")
        md.append("")
    md.append("## Aggregated scorecard\n")
    md.append(f"**Winner:** `{agg['winner']}`  ")
    md.append(f"**Ranking:** {' > '.join(agg['ranking']) or '(none)'}\n")
    md.append("| Debater | " + " | ".join(DIMENSIONS) + " | Total |")
    md.append("|---" * (len(DIMENSIONS) + 2) + "|")
    for d_id, data in agg["per_debater"].items():
        cells = [
            str(data["dimensions"][dim]["mean"] if data["dimensions"][dim]["mean"] is not None else "—")
            for dim in DIMENSIONS
        ]
        md.append(f"| {d_id} | " + " | ".join(cells) + f" | {data['total']} |")
    if agg["outliers"]:
        md.append("\n### Outlier judge scores\n")
        for o in agg["outliers"]:
            md.append(
                f"- {o['judge_id']} on {o['debater_id']}/{o['dimension']}: "
                f"{o['score']} (mean {o['mean']}, z={o['z']})"
            )
    (out_dir / "transcript.md").write_text("\n".join(md), encoding="utf-8")
