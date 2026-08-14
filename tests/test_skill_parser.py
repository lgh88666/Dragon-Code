from pathlib import Path

import pytest

from dragon_code.skills.parser import SkillParseError, parse_skill_file, render_skill_prompt


def write_skill(path: Path, header: str, body: str = "执行：$ARGUMENTS") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{header}\n---\n{body}\n", encoding="utf-8")
    return path


def test_parse_valid_skill_and_replace_arguments(tmp_path: Path):
    path = write_skill(
        tmp_path / "SKILL.md",
        "name: demo-skill\ndescription: 演示\nallowedTools: [Read]\nmode: fork\ncontext: recent",
    )
    skill = parse_skill_file(path, "project")

    assert skill.name == "demo-skill"
    assert skill.allowed_tools == ("Read",)
    assert skill.mode == "fork"
    assert render_skill_prompt(skill, "保留空格 参数") == "执行：保留空格 参数"


@pytest.mark.parametrize(
    "header",
    [
        "description: 缺名称",
        "name: BAD_NAME\ndescription: 非法名称",
        "name: demo\ndescription: x\nmode: other",
        "name: demo\ndescription: x\ncontext: other",
        "name: demo\ndescription: x\nallowedTools: Read",
    ],
)
def test_parse_rejects_invalid_metadata(tmp_path: Path, header: str):
    path = write_skill(tmp_path / "SKILL.md", header)
    with pytest.raises(SkillParseError) as error:
        parse_skill_file(path, "project")
    assert str(path.resolve()) in str(error.value)


def test_parse_rejects_broken_yaml_and_missing_frontmatter(tmp_path: Path):
    broken = tmp_path / "broken.md"
    broken.write_text("---\nname: [\n---\n正文", encoding="utf-8")
    plain = tmp_path / "plain.md"
    plain.write_text("正文", encoding="utf-8")

    with pytest.raises(SkillParseError):
        parse_skill_file(broken, "project")
    with pytest.raises(SkillParseError):
        parse_skill_file(plain, "project")


def test_parse_rejects_oversized_file(tmp_path: Path):
    path = tmp_path / "SKILL.md"
    path.write_text("x" * (256 * 1024 + 1), encoding="utf-8")
    with pytest.raises(SkillParseError, match="256KB"):
        parse_skill_file(path, "project")
