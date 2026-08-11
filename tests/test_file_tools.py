"""Read、Write、Edit 与路径边界测试。"""

import os

import pytest

from dragon_code.models import ToolCall
from dragon_code.tools.file_tools import EditTool, ReadTool, WriteTool


async def test_read_adds_line_numbers_and_reports_missing(tmp_path):
    path = tmp_path / "demo.txt"
    path.write_text("甲\n乙\n", encoding="utf-8")
    result = await ReadTool(tmp_path).execute(ToolCall("1", "Read", {"path": "demo.txt"}))
    missing = await ReadTool(tmp_path).execute(ToolCall("2", "Read", {"path": "missing.txt"}))
    assert "1 | 甲" in result.content
    assert "2 | 乙" in result.content
    assert missing.error_code == "not_found"


async def test_read_reports_directory_and_non_utf8(tmp_path):
    binary = tmp_path / "binary.dat"
    binary.write_bytes(b"\xff\xfe")
    directory = await ReadTool(tmp_path).execute(ToolCall("1", "Read", {"path": "."}))
    encoded = await ReadTool(tmp_path).execute(ToolCall("2", "Read", {"path": "binary.dat"}))
    assert directory.error_code == "not_file"
    assert encoded.error_code == "encoding_error"


async def test_write_creates_parent_and_overwrites(tmp_path):
    tool = WriteTool(tmp_path)
    call = ToolCall("1", "Write", {"path": "nested/demo.txt", "content": "第一版"})
    assert (await tool.execute(call)).success
    call.arguments["content"] = "第二版"
    assert (await tool.execute(call)).success
    assert (tmp_path / "nested/demo.txt").read_text(encoding="utf-8") == "第二版"


async def test_edit_requires_unique_match(tmp_path):
    path = tmp_path / "demo.txt"
    tool = EditTool(tmp_path)
    path.write_text("唯一内容", encoding="utf-8")
    success = await tool.execute(
        ToolCall("1", "Edit", {"path": "demo.txt", "old_text": "唯一", "new_text": "新"})
    )
    zero = await tool.execute(
        ToolCall("2", "Edit", {"path": "demo.txt", "old_text": "没有", "new_text": "x"})
    )
    path.write_text("重复 重复", encoding="utf-8")
    many = await tool.execute(
        ToolCall("3", "Edit", {"path": "demo.txt", "old_text": "重复", "new_text": "x"})
    )
    assert success.success
    assert "实际匹配 0 次" in zero.error_message
    assert "实际匹配 2 次" in many.error_message
    assert path.read_text(encoding="utf-8") == "重复 重复"


def test_edit_definition_requires_read_and_unique_match(tmp_path):
    definition = EditTool(tmp_path).definition()

    assert "编辑前必须先使用 Read" in definition.description
    assert "恰好匹配一次" in definition.description
    assert "已经通过 Read 确认" in definition.input_schema["properties"]["old_text"]["description"]


async def test_file_tools_reject_outside_path(tmp_path):
    outside = tmp_path.parent / "outside-dragon-test.txt"
    write_result = await WriteTool(tmp_path).execute(
        ToolCall("1", "Write", {"path": str(outside), "content": "不应写入"})
    )
    outside.write_text("outside", encoding="utf-8")
    read_result = await ReadTool(tmp_path).execute(ToolCall("2", "Read", {"path": str(outside)}))
    edit_result = await EditTool(tmp_path).execute(
        ToolCall(
            "3",
            "Edit",
            {"path": str(outside), "old_text": "outside", "new_text": "changed"},
        )
    )
    assert write_result.error_code == "path_outside_workspace"
    assert read_result.error_code == "path_outside_workspace"
    assert edit_result.error_code == "path_outside_workspace"
    assert outside.read_text(encoding="utf-8") == "outside"
    outside.unlink()


async def test_read_returns_complete_large_file(tmp_path):
    path = tmp_path / "large.txt"
    path.write_text("\n".join(f"line-{index}" for index in range(2100)), encoding="utf-8")
    result = await ReadTool(tmp_path).execute(ToolCall("1", "Read", {"path": str(path)}))
    assert result.success
    assert result.truncated is False
    assert result.metadata["line_count"] == 2100
    assert "line-2099" in result.content


async def test_read_can_page_through_saved_large_results(tmp_path):
    path = tmp_path / "large.txt"
    path.write_text("\n".join(f"line-{index}" for index in range(500)), encoding="utf-8")

    result = await ReadTool(tmp_path).execute(
        ToolCall("1", "Read", {"path": str(path), "offset": 451, "limit": 50})
    )

    assert result.success
    assert result.content.splitlines()[0].startswith(" 451 | line-450")
    assert result.content.splitlines()[-1].startswith(" 500 | line-499")
    assert result.metadata["line_count"] == 500
    assert result.metadata["returned_lines"] == 50
    assert result.metadata["has_more"] is False


async def test_symlink_cannot_escape_workspace(tmp_path):
    outside = tmp_path.parent / "outside-symlink-target.txt"
    outside.write_text("secret", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        outside.unlink()
        pytest.skip("当前平台不允许创建符号链接")
    try:
        result = await ReadTool(tmp_path).execute(ToolCall("1", "Read", {"path": "link.txt"}))
        assert result.error_code == "path_outside_workspace"
    finally:
        if link.exists() or os.path.lexists(link):
            link.unlink()
        outside.unlink()


async def test_read_can_use_extra_memory_root_but_other_tools_cannot(tmp_path):
    project = tmp_path / "project"
    memory = tmp_path / "home" / ".dragon-code" / "memory"
    project.mkdir()
    memory.mkdir(parents=True)
    note = memory / "user_preference_short.md"
    note.write_text("remember-short", encoding="utf-8")

    read_result = await ReadTool(project, [memory]).execute(
        ToolCall("1", "Read", {"path": str(note)})
    )
    write_result = await WriteTool(project).execute(
        ToolCall("2", "Write", {"path": str(note), "content": "changed"})
    )

    assert read_result.success is True
    assert "remember-short" in read_result.content
    assert write_result.error_code == "path_outside_workspace"
    assert note.read_text(encoding="utf-8") == "remember-short"
