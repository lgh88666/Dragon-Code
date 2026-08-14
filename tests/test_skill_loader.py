import json
from pathlib import Path

from dragon_code.skills import SkillLoader


def write_skill(root: Path, name: str, description: str, *, body: str = "旧内容") -> Path:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "SKILL.md"
    path.write_text(
        f"---\nname: {name}\ndescription: {description}\nallowedTools: [Read]\n---\n{body}\n",
        encoding="utf-8",
    )
    return path


def test_loader_priority_order_and_failure_isolation(tmp_path: Path):
    project = tmp_path / "project"
    home = tmp_path / "home"
    builtin = tmp_path / "builtin"
    write_skill(builtin, "same", "内置")
    write_skill(home / ".dragon-code" / "skills", "same", "用户")
    write_skill(project / ".dragon-code" / "skills", "same", "项目")
    write_skill(project / ".dragon-code" / "skills", "z-last", "有效")
    broken = project / ".dragon-code" / "skills" / "broken.md"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text("损坏", encoding="utf-8")

    loader = SkillLoader(project, user_home=home, builtin_root=builtin, base_tool_names={"Read"})
    skills, issues = loader.load_all()

    assert [skill.name for skill in skills] == ["same", "z-last"]
    assert skills[0].description == "项目"
    assert len(issues) == 1


def test_directory_tool_json_and_script_boundary(tmp_path: Path):
    project = tmp_path / "project"
    root = project / ".dragon-code" / "skills"
    path = write_skill(root, "directory-skill", "目录 Skill")
    script = path.parent / "run.py"
    script.write_text("print('{}')", encoding="utf-8")
    (path.parent / "tool.json").write_text(
        json.dumps(
            {
                "tools": [
                    {
                        "name": "demo",
                        "description": "演示工具",
                        "inputSchema": {"type": "object", "properties": {}},
                        "script": "run.py",
                        "security": {
                            "commandArguments": ["command"],
                            "pathArguments": [{"name": "path", "access": "write"}],
                        },
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    loader = SkillLoader(
        project,
        user_home=tmp_path / "home",
        builtin_root=tmp_path / "none",
        base_tool_names={"Read"},
    )
    skills, issues = loader.load_all()

    assert not issues
    tool = skills[0].custom_tools[0]
    assert tool.name == "skill__directory_skill__demo"
    assert tool.read_only is False
    assert tool.destructive is True
    assert tool.command_arguments == ("command",)
    assert tool.path_arguments[0].access == "write"

    (path.parent / "tool.json").write_text(
        json.dumps(
            {
                "tools": [
                    {
                        "name": "escape",
                        "description": "越界",
                        "inputSchema": {"type": "object"},
                        "script": "../../outside.py",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    _skills, issues = loader.load_all()
    assert issues and "逃出" in issues[0].message


def test_reload_falls_back_to_last_valid_version(tmp_path: Path):
    project = tmp_path / "project"
    path = write_skill(project / ".dragon-code" / "skills", "reload-me", "初始")
    loader = SkillLoader(
        project,
        user_home=tmp_path / "home",
        builtin_root=tmp_path / "none",
        base_tool_names={"Read"},
    )
    skills, _issues = loader.load_all()
    previous = skills[0]

    path.write_text("损坏", encoding="utf-8")
    current, issue = loader.reload_one(previous)

    assert current == previous
    assert issue is not None
    assert issue.code == "reload_failed"
