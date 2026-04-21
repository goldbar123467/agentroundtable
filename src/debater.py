"""Debater agent.

Each instance owns one model + persona + assigned position. It exposes
`research`, `opening`, `rebuttal`, `closing` methods that return raw text.
The orchestrator is responsible for filtering/scoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import brave, openrouter
from .skills import skills_prefix


@dataclass
class Debater:
    id: str
    name: str
    model: str
    position: str
    role_md: str
    prompts_md: str
    skills: list[str] = field(default_factory=lambda: ["karpathy-guidelines"])
    temperature: float = 0.6
    max_tokens: int = 1600

    # Populated during the run:
    dossier_entries: list[dict[str, str]] = field(default_factory=list)
    dossier_text: str = ""
    research_memo: str = ""

    def system_prompt(self) -> str:
        return "\n\n---\n\n".join(
            [skills_prefix(self.skills), self.role_md]
        )

    def _prompt_section(self, header: str) -> str:
        """Extract the fenced block under `## {header}` from prompts.md."""
        target = f"## {header}".lower()
        lines = self.prompts_md.splitlines()
        for i, line in enumerate(lines):
            if line.strip().lower() == target:
                # Find the first ```...``` block after this heading.
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

    def _chat(self, user_prompt: str, *, temperature: float | None = None) -> str:
        return openrouter.chat(
            self.model,
            [
                {"role": "system", "content": self.system_prompt()},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature if temperature is None else temperature,
            max_tokens=self.max_tokens,
        )

    # --- phases ------------------------------------------------------------

    def run_research(self, topic: str, *, results_count: int) -> None:
        """Query Brave, store dossier, and produce a research memo."""
        # Brave caps queries at 400 chars; the full topic+position can blow past
        # that when the topic is long (e.g. a pasted spec). Truncate to stay inside.
        query = f"{topic} {self.position}"
        if len(query) > 380:
            query = (self.position[:380]).strip()
        entries = brave.search(query, count=results_count)
        self.dossier_entries = entries
        self.dossier_text = brave.format_dossier(entries)

        template = self._prompt_section("RESEARCH")
        user = self._fill(
            template,
            topic=topic,
            position=self.position,
            persona_name=self.name,
            dossier=self.dossier_text or "(no results)",
        )
        self.research_memo = self._chat(user)

    def speak(
        self,
        phase: str,
        *,
        topic: str,
        transcript: str,
        other_debaters: str,
        word_budget: int,
    ) -> str:
        """phase ∈ {opening, rebuttal, closing}."""
        header = phase.upper()
        template = self._prompt_section(header)
        user = self._fill(
            template,
            topic=topic,
            position=self.position,
            persona_name=self.name,
            other_debaters=other_debaters,
            research_memo=self.research_memo,
            dossier=self.dossier_text,
            transcript=transcript,
            word_budget=word_budget,
        )
        return self._chat(user)
