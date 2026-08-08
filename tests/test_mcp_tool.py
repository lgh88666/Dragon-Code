"""MCP 工具命名、Schema、结果转换和错误测试。"""

import asyncio

import pytest
from mcp.types import (
    CallToolResult,
    ImageContent,
    TextContent,
    Tool,
    ToolAnnotations,
)

from dragon_code.mcp import adapt_tool
from dragon_code.models import ToolCall


class FakeCaller:
    def __init__(self, result: CallToolResult | None = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name: str, arguments: dict) -> CallToolResult:
        self.calls.append((name, arguments))
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def remote_tool(**changes) -> Tool:
    values = {
        "name": "echo",
        "description": "返回输入文本",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    }
    values.update(changes)
    return Tool(**values)


def call(arguments: dict | None = None) -> ToolCall:
    return ToolCall(
        id="call-1",
        name="mcp__local__echo",
        arguments={"text": "dragon"} if arguments is None else arguments,
    )


def test_adapt_tool_preserves_schema_and_read_only_metadata():
    caller = FakeCaller()
    tool = adapt_tool(
        "local",
        remote_tool(annotations=ToolAnnotations(readOnlyHint=True)),
        caller,
    )

    assert tool is not None
    definition = tool.definition()
    assert definition.name == "mcp__local__echo"
    assert definition.input_schema["required"] == ["text"]
    assert tool.read_only is True
    assert tool.is_concurrency_safe is True
    assert tool.destructive is False


def test_adapt_tool_uses_fallbacks_and_rejects_illegal_name():
    caller = FakeCaller()
    fallback = adapt_tool("local", remote_tool(description=None, inputSchema={}), caller)

    assert fallback is not None
    assert "local" in fallback.description
    assert fallback.input_schema == {"type": "object"}
    assert fallback.read_only is False
    assert adapt_tool("bad.server", remote_tool(), caller) is None


@pytest.mark.asyncio
async def test_execute_collects_text_and_structured_json():
    result = CallToolResult(
        content=[TextContent(text="第一段"), TextContent(text="第二段")],
        structuredContent={"answer": 42},
    )
    caller = FakeCaller(result)
    tool = adapt_tool("local", remote_tool(), caller)
    assert tool is not None

    value = await tool.execute(call())

    assert value.success is True
    assert "第一段\n\n第二段" in value.content
    assert '"answer": 42' in value.content
    assert caller.calls == [("echo", {"text": "dragon"})]


@pytest.mark.asyncio
async def test_execute_reports_unsupported_only_content():
    result = CallToolResult(
        content=[ImageContent(data="base64", mimeType="image/png")],
    )
    tool = adapt_tool("local", remote_tool(), FakeCaller(result))
    assert tool is not None

    value = await tool.execute(call())

    assert value.success is False
    assert value.error_code == "unsupported_content"
    assert "image" in value.content


@pytest.mark.asyncio
async def test_execute_keeps_text_when_result_contains_unsupported_block():
    result = CallToolResult(
        content=[
            TextContent(text="可用文本"),
            ImageContent(data="base64", mimeType="image/png"),
        ],
    )
    tool = adapt_tool("local", remote_tool(), FakeCaller(result))
    assert tool is not None

    value = await tool.execute(call())

    assert value.success is True
    assert "可用文本" in value.content
    assert "image" in value.content


@pytest.mark.asyncio
async def test_execute_maps_remote_error_and_preserves_content():
    result = CallToolResult(content=[TextContent(text="参数不正确")], isError=True)
    tool = adapt_tool("local", remote_tool(), FakeCaller(result))
    assert tool is not None

    value = await tool.execute(call())

    assert value.success is False
    assert value.error_code == "mcp_remote_error"
    assert value.content == "参数不正确"


@pytest.mark.asyncio
async def test_execute_returns_safe_error_for_sdk_exception():
    tool = adapt_tool("local", remote_tool(), FakeCaller(error=RuntimeError("Bearer secret")))
    assert tool is not None

    value = await tool.execute(call())

    assert value.success is False
    assert value.error_code == "mcp_error"
    assert "secret" not in value.error_message


@pytest.mark.asyncio
async def test_execute_times_out(monkeypatch: pytest.MonkeyPatch):
    class SlowCaller:
        async def call_tool(self, name: str, arguments: dict) -> CallToolResult:
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    tool = adapt_tool("local", remote_tool(), SlowCaller())
    assert tool is not None
    monkeypatch.setattr(tool, "timeout_seconds", 0.01)

    value = await tool.execute(call())

    assert value.success is False
    assert value.error_code == "timeout"


@pytest.mark.asyncio
async def test_execute_keeps_complete_long_result():
    result = CallToolResult(content=[TextContent(text="x" * 100_100)])
    tool = adapt_tool("local", remote_tool(), FakeCaller(result))
    assert tool is not None

    value = await tool.execute(call())

    assert value.success is True
    assert value.truncated is False
    assert value.content == "x" * 100_100


@pytest.mark.asyncio
async def test_execute_rejects_missing_arguments():
    tool = adapt_tool("local", remote_tool(), FakeCaller())
    assert tool is not None
    bad_call = ToolCall(id="call-1", name=tool.name, arguments=None, parse_error="bad json")

    value = await tool.execute(bad_call)

    assert value.success is False
    assert value.error_code == "invalid_json"


@pytest.mark.asyncio
async def test_execute_propagates_cancellation():
    class CancelCaller:
        async def call_tool(self, name: str, arguments: dict) -> CallToolResult:
            raise asyncio.CancelledError

    tool = adapt_tool("local", remote_tool(), CancelCaller())
    assert tool is not None

    with pytest.raises(asyncio.CancelledError):
        await tool.execute(call())
