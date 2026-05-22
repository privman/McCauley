"""Tests for the skills loader."""

from __future__ import annotations

from pathlib import Path

from app.skills import load_skills, skill_index_for_prompt


def test_load_skills_reads_frontmatter(tmp_path: Path) -> None:
    (tmp_path / "alpha.md").write_text(
        "---\nname: alpha\nwhen_to_use: when greeting\ndescription: greet\n---\n\nbody alpha"
    )
    (tmp_path / "beta.md").write_text(
        "---\nname: beta\nwhen_to_use: when farewelling\ndescription: bye\n---\n\nbody beta"
    )

    skills = load_skills(tmp_path)
    assert set(skills.keys()) == {"alpha", "beta"}
    assert skills["alpha"].body == "body alpha"
    assert skills["alpha"].when_to_use == "when greeting"


def test_load_skills_handles_missing_dir(tmp_path: Path) -> None:
    skills = load_skills(tmp_path / "nope")
    assert skills == {}


def test_skill_index_renders_for_prompt(tmp_path: Path) -> None:
    (tmp_path / "x.md").write_text(
        "---\nname: x\nwhen_to_use: at the start\ndescription: starter\n---\n\nbody"
    )
    load_skills(tmp_path)
    rendered = skill_index_for_prompt()
    assert "load_skill" in rendered
    assert "x" in rendered
    assert "at the start" in rendered
