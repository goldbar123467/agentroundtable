"""Judge agent.

Reads the full transcript + pipeline flags and returns a parsed scorecard
dict. JSON parsing is tolerant of code-fenced or prefixed responses.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from . import openrouter
from .skills import skills_prefix

JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class Judge:
    id: str
    name: str
    model: str
    role_md: str
    prompts_md: str
    skills: tuple[str, ...] = ("karpathy-guidelines",)
    temperature: float = 0.2
    max_tokens: int = 2400

    def system_prompt(self) -> str:
        return "\n\n---\n\n".join(
            [skills_prefix(list(self.skills)), self.role_md]
        )

    def _prompt_section(self, header: str) -> str:
        target = f"## {header}".lower()
        lines = self.prompts_md.splitlines()
        for i, line in enumerate(lines):
            if line.strip().lower() == target:
                in_block = False
                buf: list[str] = []
                for j in range(i + 1, len(lines)):
                    if lines[j].startswith("```"):
                        if in_block:
                            return "\n".join(buf)
                        in_block = True
                        continue
                    if in_block:
                        buf.append(lines[j])
                break
        raise KeyError(f"Prompt section '{header}' not found")

    def _fill(self, template: str, **kwargs: Any) -> str:
        out = template
        for k, v in kwargs.items():
            out = out.replace(f"{{{{{k}}}}}", str(v))
        return out

    def score(
        self,
        *,
        topic: str,
        debaters_and_positions: str,
        transcript: str,
        pipeline_flags: str,
        dossiers: str,
    ) -> dict[str, Any]:
        template = self._prompt_section("SCORE")
        user = self._fill(
            template,
            topic=topic,
            persona_name=self.name,
            judge_id=self.id,
            debaters_and_positions=debaters_and_positions,
            transcript=transcript,
            pipeline_flags=pipeline_flags,
            dossiers=dossiers,
        )
        raw = openrouter.chat(
            self.model,
            [
                {"role": "system", "content": self.system_prompt()},
                {"role": "user", "content": user},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return _parse_scorecard(raw, fallback_id=self.id, fallback_name=self.name)


def _parse_scorecard(raw: str, *, fallback_id: str, fallback_name: str) -> dict[str, Any]:
    """Best-effort JSON extraction with fallback to a raw-text stub."""
    text = raw.strip()
    # Strip a leading ```json fence if present.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = JSON_BLOCK_RE.search(raw)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {
        "judge_id": fallback_id,
        "judge_name": fallback_name,
        "parse_error": True,
        "raw": raw,
        "scores": {},
        "verdict": "",
    }
