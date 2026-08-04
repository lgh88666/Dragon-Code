from pydantic import BaseModel

from dragon_code.models import ToolCall
from dragon_code.permissions import PermissionDecision, PermissionMode
from dragon_code.permissions.engine import PermissionEngine
from dragon_code.permissions.rules import RuleStore
from dragon_code.tools.base import Tool


class EmptyArguments(BaseModel):
    pass


class DemoTool(Tool):
    name = "Demo"
    category = "filesystem"
    arguments_model = EmptyArguments


def engine(tmp_path):
    return PermissionEngine(
        tmp_path,
        RuleStore.load(tmp_path, user_home=tmp_path / "home"),
    )


def test_unknown_tool_and_invalid_arguments_are_denied(tmp_path):
    permission = engine(tmp_path)
    unknown = permission.check(ToolCall("1", "Unknown", {}), None, PermissionMode.DEFAULT)
    invalid = permission.check(ToolCall("2", "Demo", None), DemoTool(), PermissionMode.DEFAULT)

    assert unknown.decision is PermissionDecision.DENY
    assert unknown.source == "unknown_tool"
    assert invalid.source == "invalid_arguments"


def test_blacklist_cannot_be_bypassed(tmp_path):
    from dragon_code.tools.bash import BashTool

    result = engine(tmp_path).check(
        ToolCall("1", "Bash", {"command": "rm -rf /"}),
        BashTool(tmp_path),
        PermissionMode.BYPASS_PERMISSIONS,
    )
    assert result.decision is PermissionDecision.DENY
    assert result.source == "blacklist"


def test_explicit_rule_short_circuits_mode(tmp_path):
    from dragon_code.tools.bash import BashTool

    settings = tmp_path / ".dragon-code/settings.local.yaml"
    settings.parent.mkdir()
    settings.write_text("permissions:\n  allow: [Bash(git status)]\n", encoding="utf-8")
    permission = engine(tmp_path)

    result = permission.check(
        ToolCall("1", "Bash", {"command": "git status"}),
        BashTool(tmp_path),
        PermissionMode.DEFAULT,
    )
    assert result.decision is PermissionDecision.ALLOW
    assert result.source == "local_rule"


def test_sandbox_denial_happens_before_allow_rule(tmp_path):
    from dragon_code.tools.file_tools import ReadTool

    settings = tmp_path / ".dragon-code/settings.local.yaml"
    settings.parent.mkdir()
    settings.write_text("permissions:\n  allow: [Read]\n", encoding="utf-8")
    result = engine(tmp_path).check(
        ToolCall("1", "Read", {"path": "../secret.txt"}),
        ReadTool(tmp_path),
        PermissionMode.DEFAULT,
    )
    assert result.decision is PermissionDecision.DENY
    assert result.source == "sandbox"


def test_mode_matrix(tmp_path):
    from dragon_code.tools.bash import BashTool
    from dragon_code.tools.file_tools import ReadTool, WriteTool

    permission = engine(tmp_path)
    read = ToolCall("r", "Read", {"path": "missing.txt"})
    write = ToolCall("w", "Write", {"path": "new.txt", "content": "x"})
    bash = ToolCall("b", "Bash", {"command": "git status"})

    for mode in PermissionMode:
        assert permission.check(read, ReadTool(tmp_path), mode).decision is PermissionDecision.ALLOW

    assert (
        permission.check(write, WriteTool(tmp_path), PermissionMode.DEFAULT).decision
        is PermissionDecision.ASK
    )
    assert (
        permission.check(write, WriteTool(tmp_path), PermissionMode.PLAN).decision
        is PermissionDecision.ASK
    )
    assert (
        permission.check(write, WriteTool(tmp_path), PermissionMode.ACCEPT_EDITS).decision
        is PermissionDecision.ALLOW
    )
    assert (
        permission.check(write, WriteTool(tmp_path), PermissionMode.BYPASS_PERMISSIONS).decision
        is PermissionDecision.ALLOW
    )
    assert (
        permission.check(bash, BashTool(tmp_path), PermissionMode.DEFAULT).decision
        is PermissionDecision.ASK
    )
    assert (
        permission.check(bash, BashTool(tmp_path), PermissionMode.BYPASS_PERMISSIONS).decision
        is PermissionDecision.ALLOW
    )
