"""Load skill markdown files and make them available as system-prompt prefixes.

Current skills:
- `karpathy-guidelines` — vendored from forrestchang/andrej-karpathy-skills.

New skills are picked up automatically by dropping a `*.md` file in `skills/`.
"""

from __future__ import annotations

from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def load_skill(name: str) -> str:
    """Return the raw markdown of a skill by filename stem.

    Raises FileNotFoundError if the skill isn't present.
    """
    path = SKILLS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Skill not found: {path}")
    return path.read_text(encoding="utf-8")


def list_skills() -> list[str]:
    return sorted(p.stem for p in SKILLS_DIR.glob("*.md"))


def skills_prefix(names: list[str]) -> str:
    """Concatenate a set of skills into a single system-prompt prefix."""
    parts = []
    for n in names:
        parts.append(load_skill(n))
    return "\n\n---\n\n".join(parts)
