"""共享工具数据模型与 Tool 基类测试。"""

import asyncio

from pydantic import BaseModel, Field

from dragon_code.models import ChatMessage, ToolCall, ToolResult
from dragon_code.tools.base import Tool, ToolExecutionError


class DemoArguments(BaseModel):
    value: str = Field(description="演示参数")


class DemoTool(Tool):
    name = "Demo"
    description = "用于测试的工具。"
    category = "test"
    arguments_model = DemoArguments

    async def run(self, call, arguments):
        return self._success(call, arguments.value)


def test_message_lists_are_isolated():
    first = ChatMessage("user")
    second = ChatMessage("user")
    first.tool_calls.append(ToolCall("1", "Demo", {}))
    assert second.tool_calls == []


def test_tool_result_json_is_readable():
    result = ToolResult("1", "Demo", False, error_code="bad", error_message="中文错误")
    text = result.to_model_text()
    assert "中文错误" in text
    assert "\\u" not in text


def test_definition_contains_schema_and_metadata():
    definition = DemoTool().definition()
    assert definition.name == "Demo"
    assert definition.input_schema["required"] == ["value"]
    assert definition.input_schema["properties"]["value"]["description"] == "演示参数"
    assert definition.read_only is True


async def test_invalid_json_and_arguments_are_results():
    tool = DemoTool()
    invalid_json = await tool.execute(ToolCall("1", "Demo", None, "{", "JSON 不完整"))
    invalid_arguments = await tool.execute(ToolCall("2", "Demo", {"wrong": "x"}))
    assert invalid_json.error_code == "invalid_json"
    assert invalid_arguments.error_code == "invalid_arguments"


async def test_timeout_and_expected_exception_are_results():
    class SlowTool(DemoTool):
        timeout_seconds = 0.01

        async def run(self, call, arguments):
            await asyncio.sleep(0.1)
            return self._success(call, "done")

    class BrokenTool(DemoTool):
        async def run(self, call, arguments):
            raise ToolExecutionError("broken", "清晰错误")

    timeout = await SlowTool().execute(ToolCall("1", "Demo", {"value": "x"}))
    broken = await BrokenTool().execute(ToolCall("2", "Demo", {"value": "x"}))
    assert timeout.error_code == "timeout"
    assert broken.error_message == "清晰错误"
