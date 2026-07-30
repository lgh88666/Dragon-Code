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


async def test_grep_returns_file_line_and_content(tmp_path):
    (tmp_path / "code.py").write_text("first\nDragon Code\n", encoding="utf-8")
    result = await GrepTool(tmp_path).execute(
        ToolCall("1", "Grep", {"pattern": "Dragon", "path": "."})
    )
    assert "code.py:2: Dragon Code" in result.content


async def test_grep_empty_and_invalid_pattern(tmp_path):
    (tmp_path / "code.py").write_text("hello", encoding="utf-8")
    empty = await GrepTool(tmp_path).execute(ToolCall("1", "Grep", {"pattern": "none"}))
    invalid = await GrepTool(tmp_path).execute(ToolCall("2", "Grep", {"pattern": "["}))
    assert empty.success and empty.content == ""
    assert invalid.error_code == "invalid_pattern"
