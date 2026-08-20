from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = ROOT / "skills" / "ai-frontier-newsroom" / "SKILL.md"


def load_skill() -> tuple[dict[str, str], str]:
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    _, frontmatter, _ = text.split("---", maxsplit=2)
    return yaml.safe_load(frontmatter), text


def test_newsroom_skill_has_explicit_radar_scope() -> None:
    frontmatter, text = load_skill()

    assert frontmatter["name"] == "ai-frontier-newsroom"
    assert "AI Radar" in frontmatter["description"]
    assert "ai-radar-harness" in frontmatter["description"]
    assert "AI Research Observatory" in text
    assert "do not use this Skill" in text


def test_newsroom_skill_does_not_claim_bare_continuation() -> None:
    frontmatter, text = load_skill()

    assert "AI 资讯" not in frontmatter["description"]
    assert 'or "继续":' not in text
    assert "continue after Human Gate" in text

