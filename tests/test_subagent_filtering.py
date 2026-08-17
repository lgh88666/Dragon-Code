from pathlib import Path

from pydantic import BaseModel

from dragon_code.permissions import PermissionMode
from dragon_code.subagents.filtering import filter_subagent_registry
from dragon_code.subagents.models import AgentDefinition, AgentDefinitionSource, QuerySource
from dragon_code.tools.base import Tool
from dragon_code.tools.registry import ToolRegistry


class EmptyArguments(BaseModel):
    pass


def tool(name: str, *, read_only: bool = True, system: bool = False) -> Tool:
    item = Tool()
    item.name = name
    item.read_only = read_only
    item.is_system_tool = system
    item.arguments_model = EmptyArguments
    return item


def definition(*, allowed=(), denied=()) -> AgentDefinition:
    return AgentDefinition(
        "demo",
        "demo",
        "prompt",
        tuple(allowed),
        tuple(denied),
        "model",
        5,
        PermissionMode.DEFAULT,
        False,
        AgentDefinitionSource.PROJECT,
        Path("demo.md"),
    )


def registry() -> ToolRegistry:
    result = ToolRegistry()
    for item in [
        tool("Read"),
        tool("Write", read_only=False),
        tool("Agent", system=True),
        tool("TaskGet", system=True),
        tool("LoadSkill", system=True),
        tool("mcp__docs__search"),
        tool("skill__lint__run"),
        tool("Other"),
    ]:
        result.register(item)
    return result


def test_defined_subagent_removes_main_only_and_system_loader():
    filtered = filter_subagent_registry(
        registry(), definition(), source=QuerySource.DEFINED_SUBAGENT, background=False
    )

    assert filtered.names() == ["Read", "Write", "mcp__docs__search", "skill__lint__run", "Other"]


def test_background_filter_keeps_core_and_external_tools():
    filtered = filter_subagent_registry(
        registry(), definition(), source=QuerySource.DEFINED_SUBAGENT, background=True
    )

    assert filtered.names() == ["Read", "Write", "mcp__docs__search", "skill__lint__run"]


def test_role_denied_wins_and_allowed_preserves_order():
    filtered = filter_subagent_registry(
        registry(),
        definition(allowed=("Read", "Write"), denied=("Read",)),
        source=QuerySource.DEFINED_SUBAGENT,
        background=False,
    )

    assert filtered.names() == ["Write"]


def test_fork_keeps_exact_parent_order():
    original = registry()
    filtered = filter_subagent_registry(
        original, None, source=QuerySource.FORK_SUBAGENT, background=True
    )

    assert filtered.names() == original.names()
