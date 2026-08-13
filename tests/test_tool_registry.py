"""工具注册中心测试。"""

import pytest

from dragon_code.models import ToolCall
from dragon_code.tools import ToolRegistry, create_default_registry
from dragon_code.tools.file_tools import ReadTool


def test_default_registry_has_six_tools_and_metadata(tmp_path):
    definitions = create_default_registry(tmp_path).definitions()
    assert [item.name for item in definitions] == ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]
    assert all(item.description and item.input_schema for item in definitions)
    assert definitions[0].read_only is True
    assert definitions[1].destructive is True


def test_registry_subset_keeps_order_and_instances(tmp_path):
    registry = create_default_registry(tmp_path)
    subset = registry.subset({"Read", "Glob", "Grep"})

    assert [item.name for item in subset.definitions()] == ["Read", "Glob", "Grep"]
    assert subset.get("Read") is registry.get("Read")
    assert subset.get("Write") is None


def test_duplicate_registration_is_rejected(tmp_path):
    registry = ToolRegistry()
    registry.register(ReadTool(tmp_path))
    with pytest.raises(ValueError, match="工具名重复"):
        registry.register(ReadTool(tmp_path))


async def test_unknown_tool_is_a_result():
    result = await ToolRegistry().execute(ToolCall("1", "Missing", {}))
    assert result.error_code == "unknown_tool"


def test_registry_passes_extra_read_roots_only_to_read(tmp_path):
    memory = tmp_path / "memory"
    registry = create_default_registry(tmp_path, [memory])

    assert registry.get("Read").extra_read_roots == [memory.resolve()]
    assert not hasattr(registry.get("Write"), "extra_read_roots")


def test_registry_counts_builtin_and_mcp_tools(tmp_path):
    registry = create_default_registry(tmp_path)
    remote = ReadTool(tmp_path)
    remote.name = "mcp__demo__read"
    registry.register(remote)

    assert registry.counts() == (6, 1)
