from pathlib import Path

import pytest

from dragon_code.permissions import PermissionMode
from dragon_code.subagents.models import AgentDefinitionSource
from dragon_code.subagents.parser import AgentDefinitionError, parse_agent_definition


def write_definition(path: Path, frontmatter: str, body: str = "执行任务。") -> Path:
    path.write_text(f"---\n{frontmatter}\n---\n{body}\n", encoding="utf-8")
    return path


def test_parse_agent_definition_complete(tmp_path: Path):
    path = write_definition(
        tmp_path / "review.md",
        """name: review
description: 审查代码
tools: [Read, Grep]
disallowedTools: [Bash]
model: custom-model
maxTurns: 12
permissionMode: plan
background: true""",
    )

    definition = parse_agent_definition(path, AgentDefinitionSource.PROJECT)

    assert definition.name == "review"
    assert definition.allowed_tools == ("Read", "Grep")
    assert definition.disallowed_tools == ("Bash",)
    assert definition.model == "custom-model"
    assert definition.max_iterations == 12
    assert definition.permission_mode is PermissionMode.PLAN
    assert definition.background is True


def test_parse_agent_definition_defaults(tmp_path: Path):
    path = write_definition(tmp_path / "simple.md", "name: simple\ndescription: 简单角色")

    definition = parse_agent_definition(path, AgentDefinitionSource.USER)

    assert definition.model == "deepseek-v4-flash"
    assert definition.max_iterations == 50
    assert definition.permission_mode is PermissionMode.DEFAULT
    assert definition.allowed_tools == ()


@pytest.mark.parametrize(
    "frontmatter,body",
    [
        ("description: 缺名字", "正文"),
        ("name: Bad_Name\ndescription: 错误名字", "正文"),
        ("name: demo\ndescription: 描述\ntools: Read", "正文"),
        ("name: demo\ndescription: 描述\ntools: [Read, Read]", "正文"),
        ("name: demo\ndescription: 描述\nmaxTurns: true", "正文"),
        ("name: demo\ndescription: 描述\npermissionMode: invalid", "正文"),
        ("name: demo\ndescription: 描述\nbackground: 1", "正文"),
        ("name: demo\ndescription: 描述", ""),
    ],
)
def test_parse_agent_definition_rejects_invalid_fields(tmp_path: Path, frontmatter: str, body: str):
    path = write_definition(tmp_path / "bad.md", frontmatter, body)

    with pytest.raises(AgentDefinitionError):
        parse_agent_definition(path, AgentDefinitionSource.PROJECT)


def test_parse_agent_definition_rejects_broken_yaml(tmp_path: Path):
    path = tmp_path / "bad.md"
    path.write_text("---\nname: [\n---\n正文", encoding="utf-8")

    with pytest.raises(AgentDefinitionError):
        parse_agent_definition(path, AgentDefinitionSource.PROJECT)
