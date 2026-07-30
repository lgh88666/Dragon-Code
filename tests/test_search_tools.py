"""Glob 与 Grep 测试。"""

from dragon_code.models import ToolCall
from dragon_code.tools.search_tools import GlobTool, GrepTool


async def test_glob_returns_sorted_files(tmp_path):
    (tmp_path / "b.py").write_text("", encoding="utf-8")
    (tmp_path / "a.py").write_text("", encoding="utf-8")
    (tmp_path / "folder").mkdir()
    result = await GlobTool(tmp_path).execute(ToolCall("1", "Glob", {"pattern": "**/*.py"}))
    assert result.content.splitlines() == ["a.py", "b.py"]


async def test_glob_rejects_parent_pattern(tmp_path):
    result = await GlobTool(tmp_path).execute(ToolCall("1", "Glob", {"pattern": "../*.py"}))
    assert result.error_code == "path_outside_workspace"
    empty = await GlobTool(tmp_path).execute(ToolCall("2", "Glob", {"pattern": "*.missing"}))
    assert empty.success and empty.content == ""


async def test_grep_returns_file_line_and_content(tmp_path):
    (tmp_path / "code.py").write_text("first\nDragon Code\n", encoding="utf-8")
    result = await GrepTool(tmp_path).execute(
        ToolCall("1", "Grep", {"pattern": "Dragon", "path": "."})
    )
    assert "code.py:2: Dragon Code" in result.content
    single_file = await GrepTool(tmp_path).execute(
        ToolCall("2", "Grep", {"pattern": "first", "path": "code.py"})
    )
    assert "code.py:1: first" in single_file.content


async def test_grep_empty_and_invalid_pattern(tmp_path):
    (tmp_path / "code.py").write_text("hello", encoding="utf-8")
    empty = await GrepTool(tmp_path).execute(ToolCall("1", "Grep", {"pattern": "none"}))
    invalid = await GrepTool(tmp_path).execute(ToolCall("2", "Grep", {"pattern": "["}))
    assert empty.success and empty.content == ""
    assert invalid.error_code == "invalid_pattern"
    outside = await GrepTool(tmp_path).execute(
        ToolCall("3", "Grep", {"pattern": "hello", "path": "../"})
    )
    assert outside.error_code == "path_outside_workspace"


async def test_search_results_are_limited_and_skip_git(tmp_path):
    for index in range(205):
        (tmp_path / f"{index:03}.txt").write_text("needle", encoding="utf-8")
    hidden = tmp_path / ".git"
    hidden.mkdir()
    (hidden / "ignored.txt").write_text("needle", encoding="utf-8")

    glob_result = await GlobTool(tmp_path).execute(ToolCall("1", "Glob", {"pattern": "**/*.txt"}))
    grep_result = await GrepTool(tmp_path).execute(ToolCall("2", "Grep", {"pattern": "needle"}))
    assert glob_result.truncated and len(glob_result.content.splitlines()) == 200
    assert grep_result.truncated and len(grep_result.content.splitlines()) == 200
    assert ".git" not in grep_result.content
