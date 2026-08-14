from pathlib import Path

from dragon_code.skills import SkillDefinition, SkillLoader, SkillManager, SkillRuntime


def definition(name: str, tools: tuple[str, ...] = ()) -> SkillDefinition:
    path = Path(f"/{name}/SKILL.md")
    return SkillDefinition(
        name=name,
        description=f"{name} 描述",
        prompt_body=f"{name}: $ARGUMENTS",
        allowed_tools=tools,
        mode="inline",
        model=None,
        context="full",
        source_level="project",
        source_path=path,
        skill_dir=path.parent,
    )


def test_runtime_activation_reminder_union_and_clear():
    runtime = SkillRuntime()
    assert runtime.allowed_tool_names() is None

    runtime.activate(definition("one", ("Read",)), "参数")
    runtime.activate(definition("two", ("Grep",)))
    runtime.activate(definition("one", ("Read",)), "新参数")

    assert [item.name for item in runtime.active_skills()] == ["one", "two"]
    assert runtime.allowed_tool_names() == {"Read", "Grep"}
    assert runtime.reminder_text().count("已激活 Skill") == 2
    assert "新参数" in runtime.reminder_text()
    runtime.clear()
    assert runtime.active_skills() == []


def test_activated_empty_whitelist_is_not_unrestricted():
    runtime = SkillRuntime()
    runtime.activate(definition("empty"))
    assert runtime.allowed_tool_names() == set()


def test_manager_snapshot_and_summary_are_stable(tmp_path: Path):
    project = tmp_path / "project"
    root = project / ".dragon-code" / "skills"
    for name in ["zeta", "alpha"]:
        directory = root / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {name} 描述\nallowedTools: []\n---\n正文",
            encoding="utf-8",
        )
    manager = SkillManager(
        SkillLoader(project, user_home=tmp_path / "home", builtin_root=tmp_path / "none")
    )
    first = manager.reload()
    first_summary = manager.summary_text()
    second = manager.reload()

    assert [skill.name for skill in first.skills] == ["alpha", "zeta"]
    assert first_summary == manager.summary_text()
    assert first.skills == second.skills
