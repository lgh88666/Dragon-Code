from pathlib import Path

import pytest

from dragon_code.subagents.catalog import (
    AgentDefinitionLoader,
    BuiltinAgentDefinitionError,
)


def write_agent(root: Path, name: str, description: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n执行 {name}\n",
        encoding="utf-8",
    )


def test_catalog_loads_builtins_in_stable_order(tmp_path: Path):
    catalog = AgentDefinitionLoader(tmp_path, user_home=tmp_path / "home").load()

    assert [item.name for item in catalog.list_definitions()] == ["explore", "plan", "verify"]
    assert catalog.issues() == []


def test_catalog_higher_source_overrides_lower(tmp_path: Path):
    builtin = tmp_path / "builtin"
    home = tmp_path / "home"
    write_agent(builtin, "same", "内置")
    write_agent(home / ".dragon-code" / "agents", "same", "用户")
    write_agent(tmp_path / ".dragon-code" / "agents", "same", "项目")

    catalog = AgentDefinitionLoader(
        tmp_path,
        user_home=home,
        builtin_root=builtin,
    ).load()

    assert catalog.get("same").description == "项目"


def test_catalog_skips_broken_project_file(tmp_path: Path):
    builtin = tmp_path / "builtin"
    write_agent(builtin, "ok", "正常")
    project = tmp_path / ".dragon-code" / "agents"
    project.mkdir(parents=True)
    (project / "bad.md").write_text("broken", encoding="utf-8")

    catalog = AgentDefinitionLoader(tmp_path, builtin_root=builtin).load()

    assert catalog.get("ok") is not None
    assert len(catalog.issues()) == 1


def test_catalog_rejects_broken_builtin(tmp_path: Path):
    builtin = tmp_path / "builtin"
    builtin.mkdir()
    (builtin / "bad.md").write_text("broken", encoding="utf-8")

    with pytest.raises(BuiltinAgentDefinitionError):
        AgentDefinitionLoader(tmp_path, builtin_root=builtin).load()
