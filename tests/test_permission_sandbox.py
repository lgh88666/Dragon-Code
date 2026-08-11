import os

import pytest

from dragon_code.models import ToolCall
from dragon_code.permissions import PermissionDecision
from dragon_code.permissions.sandbox import PathSandbox, extract_target


def call(name: str, **arguments) -> ToolCall:
    return ToolCall("call-1", name, arguments)


@pytest.mark.parametrize(
    ("tool_call", "expected"),
    [
        (call("Read", path="README.md"), "README.md"),
        (call("Write", path="src/new.py"), "src/new.py"),
        (call("Edit", path="src/main.py"), "src/main.py"),
        (call("Grep", pattern="x"), "."),
        (call("Grep", pattern="x", path="src"), "src"),
        (call("Glob", pattern="**/*.py"), "."),
        (call("Glob", pattern="src/**/*.py"), "src"),
    ],
)
def test_extract_target(tool_call, expected):
    assert extract_target(tool_call) == expected


def test_bash_does_not_use_path_sandbox():
    assert extract_target(call("Bash", command="pwd")) is None


@pytest.mark.parametrize(
    "tool_call",
    [
        ToolCall("1", "Read", None),
        call("Read", path=123),
        call("Glob", pattern="../**/*.py"),
    ],
)
def test_invalid_target_is_denied(tool_call):
    result = extract_target(tool_call)
    assert result.decision is PermissionDecision.DENY


def test_project_paths_and_new_nested_path_are_allowed(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "existing.txt").write_text("ok", encoding="utf-8")
    sandbox = PathSandbox(root)

    assert sandbox.check(call("Read", path="existing.txt")) is None
    assert sandbox.check(call("Write", path="new/deep/file.txt")) is None


def test_absolute_and_parent_escape_are_denied(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    sandbox = PathSandbox(root)

    assert sandbox.check(call("Read", path=str(outside))).decision is PermissionDecision.DENY
    assert sandbox.check(call("Read", path="../outside.txt")).decision is PermissionDecision.DENY


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="当前平台不支持符号链接")
def test_symlink_escape_is_denied(tmp_path):
    root = tmp_path / "project"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("当前用户没有创建符号链接的权限")

    result = PathSandbox(root).check(call("Write", path="link/new.txt"))
    assert result.decision is PermissionDecision.DENY


def test_extra_root_is_read_only(tmp_path):
    root = tmp_path / "project"
    memory = tmp_path / "home" / ".dragon-code" / "memory"
    root.mkdir()
    memory.mkdir(parents=True)
    note = memory / "note.md"
    note.write_text("memory", encoding="utf-8")
    sandbox = PathSandbox(root, [memory])

    assert sandbox.check(call("Read", path=str(note))) is None
    for tool_name in ["Write", "Edit", "Grep"]:
        result = sandbox.check(call(tool_name, path=str(note), pattern="memory"))
        assert result.decision is PermissionDecision.DENY
