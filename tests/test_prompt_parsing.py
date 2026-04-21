"""Verify role + prompts.md section extraction works for debater and judge."""

from __future__ import annotations

from pathlib import Path

from src.debater import Debater
from src.judge import Judge

ROOT = Path(__file__).resolve().parent.parent
ROLES = ROOT / "roles"


def _debater():
    return Debater(
        id="D1",
        name="Aria",
        model="anthropic/claude-sonnet-4.5",
        position="Yes",
        role_md=(ROLES / "debater" / "role.md").read_text(),
        prompts_md=(ROLES / "debater" / "prompts.md").read_text(),
    )


def _judge():
    return Judge(
        id="J1",
        name="Hon. Ito",
        model="anthropic/claude-opus-4.5",
        role_md=(ROLES / "judge" / "role.md").read_text(),
        prompts_md=(ROLES / "judge" / "prompts.md").read_text(),
    )


def test_debater_sections_present():
    d = _debater()
    for header in ("RESEARCH", "OPENING", "REBUTTAL", "CLOSING"):
        text = d._prompt_section(header)
        assert "{{topic}}" in text, f"{header} missing topic placeholder"


def test_judge_sections_present():
    j = _judge()
    text = j._prompt_section("SCORE")
    assert "{{transcript}}" in text
    assert "{{judge_id}}" in text


def test_skills_are_injected():
    d = _debater()
    sp = d.system_prompt()
    assert "Karpathy Guidelines" in sp
    assert "Role: Debater" in sp
