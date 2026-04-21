"""CLI entrypoint.

Usage:
    python -m src.main \
        --topic "Should municipal broadband replace ISP monopolies?" \
        --positions positions.yaml

If --positions is omitted, the orchestrator asks the first debater's model
to generate four distinct positions on the topic.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .openrouter import chat
from .orchestrator import ROOT, Orchestrator


def _auto_positions(topic: str, model: str, debater_ids: list[str]) -> dict[str, str]:
    """Ask a model to produce four distinct positions keyed by debater id."""
    sys_prompt = (
        "You assign debate positions. Return strict JSON mapping the given "
        "debater ids to distinct, clearly-stated positions on the topic. "
        "Aim for variety: pro, con, reformist, orthogonal/contrarian. "
        "Each position must be a single sentence stating what the debater "
        "will advocate for."
    )
    user = (
        f"TOPIC: {topic}\nDEBATER IDS: {debater_ids}\n"
        'Output JSON only, e.g. {"D1": "...", "D2": "...", "D3": "...", "D4": "..."}.'
    )
    raw = chat(
        model,
        [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user},
        ],
        temperature=0.3,
        max_tokens=400,
    ).strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip("`").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(f"Could not parse auto-generated positions: {e}\nRaw: {raw}")
    missing = [d for d in debater_ids if d not in data]
    if missing:
        raise SystemExit(f"Auto positions missing debaters: {missing}\nRaw: {raw}")
    return {d: str(data[d]).strip() for d in debater_ids}


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser(prog="agentroundtable")
    parser.add_argument("--topic", required=True, help="Debate topic / motion")
    parser.add_argument(
        "--positions",
        help="Path to YAML mapping debater id → position. Omit to auto-generate.",
    )
    parser.add_argument(
        "--config",
        default=str(ROOT / "config.yaml"),
        help="Path to config.yaml",
    )
    args = parser.parse_args(argv)

    orch = Orchestrator(Path(args.config))
    debater_ids = [d["id"] for d in orch.config["debaters"]]

    if args.positions:
        positions_raw = yaml.safe_load(Path(args.positions).read_text(encoding="utf-8"))
        if not isinstance(positions_raw, dict):
            raise SystemExit("Positions file must be a mapping of id → position.")
        positions = {str(k): str(v) for k, v in positions_raw.items()}
    else:
        first_model = orch.config["debaters"][0]["model"]
        print(f"[positions] Auto-generating via {first_model} ...")
        positions = _auto_positions(args.topic, first_model, debater_ids)
        for k, v in positions.items():
            print(f"  {k}: {v}")

    out_dir = orch.run(args.topic, positions)
    print(f"\nArtifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
