"""Read、Write、Edit 与路径边界测试。"""

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


async def test_file_tools_reject_outside_path(tmp_path):
    outside = tmp_path.parent / "outside-dragon-test.txt"
    result = await WriteTool(tmp_path).execute(
        ToolCall("1", "Write", {"path": str(outside), "content": "不应写入"})
    )
    assert result.error_code == "path_outside_workspace"
    assert not outside.exists()
