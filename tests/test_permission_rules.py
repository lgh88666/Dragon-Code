from pathlib import Path

import pytest

from dragon_code.models import ToolCall
from dragon_code.permissions import PermissionDecision, PermissionMode
from dragon_code.permissions.rules import (
    RuleParseError,
    RuleStore,
    make_exact_rule,
    parse_rule,
    rule_matches,
)


def call(name: str, **arguments) -> ToolCall:
    return ToolCall("call-1", name, arguments)


def test_parse_rule_with_and_without_pattern():
    all_bash = parse_rule("Bash", PermissionDecision.ALLOW)
    git = parse_rule("Bash(git *)", PermissionDecision.DENY)

    assert all_bash.pattern is None
    assert git.tool_name == "Bash"
    assert git.pattern == "git *"
    assert git.raw == "Bash(git *)"


def test_mcp_rule_uses_complete_tool_name():
    raw = "mcp__github__create_issue"
    rule = parse_rule(raw, PermissionDecision.ALLOW)
    tool_call = call(raw, title="demo")

    assert rule.pattern is None
    assert rule_matches(rule, tool_call, Path.cwd()) is True
    assert make_exact_rule(tool_call, Path.cwd()) == raw


@pytest.mark.parametrize(
    "raw",
    [
        "mcp__missingtool",
        "mcp__bad.server__tool",
        "mcp__server__bad.tool",
        "mcp__server__tool(pattern)",
    ],
)
def test_mcp_rule_rejects_incomplete_or_pattern_form(raw):
    with pytest.raises(RuleParseError):
        parse_rule(raw, PermissionDecision.ALLOW)


@pytest.mark.parametrize("raw", ["", "Unknown(x)", "Bash(", "Bash()"])
def test_parse_rule_rejects_invalid_text(raw):
    with pytest.raises(RuleParseError):
        parse_rule(raw, PermissionDecision.ALLOW)


def test_rule_keeps_right_parentheses_inside_command():
    rule = parse_rule("Bash(python -c print('ok'))", PermissionDecision.ALLOW)
    assert rule.pattern == "python -c print('ok')"


def test_make_exact_rule_escapes_command_wildcards(tmp_path):
    exact = make_exact_rule(call("Bash", command="rg *.py"), tmp_path)
    rule = parse_rule(exact, PermissionDecision.ALLOW)

    assert exact == r"Bash(rg \*.py)"
    assert rule_matches(rule, call("Bash", command="rg *.py"), tmp_path)
    assert not rule_matches(rule, call("Bash", command="rg test.py"), tmp_path)


def test_file_star_does_not_cross_directory(tmp_path):
    rule = parse_rule("Read(src/*.py)", PermissionDecision.ALLOW)
    assert rule_matches(rule, call("Read", path="src/main.py"), tmp_path)
    assert not rule_matches(rule, call("Read", path="src/pkg/main.py"), tmp_path)


def test_file_double_star_crosses_directory(tmp_path):
    rule = parse_rule("Read(src/**)", PermissionDecision.ALLOW)
    assert rule_matches(rule, call("Read", path="src/pkg/main.py"), tmp_path)


def test_command_star_matches_full_command_text(tmp_path):
    rule = parse_rule("Bash(git *)", PermissionDecision.ALLOW)
    assert rule_matches(rule, call("Bash", command="git status --short"), tmp_path)
    assert not rule_matches(rule, call("Bash", command="uv run pytest"), tmp_path)


def write_settings(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_load_skips_invalid_yaml_and_invalid_rule(tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    write_settings(home / ".dragon-code/settings.yaml", "permissions: [")
    write_settings(
        project / ".dragon-code/settings.yaml",
        "permissions:\n  allow:\n    - Unknown(x)\n    - Bash(git status)\n",
    )

    store = RuleStore.load(project, user_home=home)
    assert store.match(call("Bash", command="git status")).decision is PermissionDecision.ALLOW


def test_local_layer_overrides_project_and_user(tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    write_settings(
        home / ".dragon-code/settings.yaml",
        "permissions:\n  deny: [Bash(git status)]\n",
    )
    write_settings(
        project / ".dragon-code/settings.yaml",
        "permissions:\n  deny: [Bash(git status)]\n",
    )
    write_settings(
        project / ".dragon-code/settings.local.yaml",
        "permissions:\n  allow: [Bash(git status)]\n",
    )

    result = RuleStore.load(project, user_home=home).match(call("Bash", command="git status"))
    assert result.decision is PermissionDecision.ALLOW
    assert result.source == "local_rule"


def test_deny_wins_inside_same_layer(tmp_path):
    project = tmp_path / "project"
    write_settings(
        project / ".dragon-code/settings.local.yaml",
        "permissions:\n  allow: [Bash(git *)]\n  deny: [Bash(git status)]\n",
    )
    result = RuleStore.load(project, user_home=tmp_path / "home").match(
        call("Bash", command="git status")
    )
    assert result.decision is PermissionDecision.DENY


def test_default_mode_uses_nearest_valid_layer(tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    write_settings(
        home / ".dragon-code/settings.yaml",
        "permissions:\n  mode: bypassPermissions\n",
    )
    write_settings(
        project / ".dragon-code/settings.yaml",
        "permissions:\n  mode: acceptEdits\n",
    )
    assert RuleStore.load(project, user_home=home).default_mode() is PermissionMode.ACCEPT_EDITS


def test_missing_or_invalid_mode_falls_back_to_default(tmp_path):
    project = tmp_path / "project"
    write_settings(
        project / ".dragon-code/settings.local.yaml",
        "permissions:\n  mode: unknown\n",
    )
    store = RuleStore.load(project, user_home=tmp_path / "home")
    assert store.default_mode() is PermissionMode.DEFAULT


def test_save_local_allow_preserves_fields_and_deduplicates(tmp_path):
    project = tmp_path / "project"
    local_path = project / ".dragon-code/settings.local.yaml"
    write_settings(
        local_path,
        "other: keep\npermissions:\n  deny: [Read(.env)]\n",
    )
    store = RuleStore.load(project, user_home=tmp_path / "home")

    store.save_local_allow("Bash(git status)")
    store.save_local_allow("Bash(git status)")

    text = local_path.read_text(encoding="utf-8")
    assert "other: keep" in text
    assert "Read(.env)" in text
    assert text.count("Bash(git status)") == 1
    assert store.match(call("Bash", command="git status")).decision is PermissionDecision.ALLOW
