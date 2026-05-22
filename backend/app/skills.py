"""Skills loader (design.md §5.1).

Loads markdown files from settings.skills_dir at app startup. Each file has
frontmatter (`name`, `when_to_use`, `description`). The orchestrator gets a
**skill index** (just names + when_to_use, ~50 tokens each) injected into
the cached system prompt; the full body is loaded on demand via the
`load_skill` tool.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import frontmatter

from app.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Skill:
    name: str
    when_to_use: str
    description: str
    body: str


_skills: dict[str, Skill] | None = None


def load_skills(skills_dir: Path | None = None) -> dict[str, Skill]:
    """Load (or reload) skills from disk. Idempotent."""
    global _skills
    root = skills_dir or get_settings().skills_dir
    if not root.exists():
        logger.warning("skills dir not found: %s — no skills loaded", root)
        _skills = {}
        return _skills

    loaded: dict[str, Skill] = {}
    for path in sorted(root.glob("*.md")):
        post = frontmatter.load(path)
        name = post.get("name") or path.stem
        when = post.get("when_to_use") or ""
        desc = post.get("description") or ""
        loaded[name] = Skill(
            name=name,
            when_to_use=when,
            description=desc,
            body=post.content.strip(),
        )
    logger.info("loaded %d skills from %s", len(loaded), root)
    _skills = loaded
    return loaded


def get_skills() -> dict[str, Skill]:
    return _skills if _skills is not None else load_skills()


def skill_index_for_prompt() -> str:
    """Short, cacheable list of skill names + when_to_use for the system prompt."""
    skills = get_skills()
    if not skills:
        return "(no skills available)"
    lines = ["Available coaching skills (call load_skill(name) to read the body):"]
    for s in sorted(skills.values(), key=lambda x: x.name):
        lines.append(f"- `{s.name}` — {s.when_to_use}")
    return "\n".join(lines)


def load_skill(name: str) -> Skill | None:
    return get_skills().get(name)
