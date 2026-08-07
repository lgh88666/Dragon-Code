"""把远端 MCP 工具适配为 Dragon Code 的统一 Tool。"""

import asyncio
import json
import re
from typing import Protocol

from mcp.types import CallToolResult, TextContent
from mcp.types import Tool as RemoteTool

from dragon_code.models import ToolCall, ToolDefinition, ToolResult
from dragon_code.tools.base import Tool

CALL_TIMEOUT_SECONDS = 30.0
MAX_RESULT_CHARS = 100_000
VALID_TOOL_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


class McpCaller(Protocol):
    """McpTool 调用远端时真正需要的最小接口。"""

    async def call_tool(self, name: str, arguments: dict) -> CallToolResult: ...


class McpTool(Tool):
    """一个已经完成命名和 Schema 转换的远端工具。"""

    category = "mcp"
    timeout_seconds = CALL_TIMEOUT_SECONDS

    def __init__(
        self,
        *,
        name: str,
        remote_name: str,
        server_name: str,
        description: str,
        input_schema: dict,
        read_only: bool,
        caller: McpCaller,
    ):
        self.name = name
        self.remote_name = remote_name
        self.server_name = server_name
        self.description = description
        self.input_schema = input_schema
        self.read_only = read_only
        self.destructive = not read_only
        self.is_concurrency_safe = read_only
        self.caller = caller

    def definition(self) -> ToolDefinition:
        """MCP 已经提供 JSON Schema，直接交给模型。"""

        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
            category=self.category,
            read_only=self.read_only,
            destructive=self.destructive,
            is_concurrency_safe=self.is_concurrency_safe,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """调用远端 Server，并把所有失败包装成结构化结果。"""

        if call.arguments is None:
            return self._failure(
                call,
                "invalid_json",
                call.parse_error or "MCP 工具参数不是有效 JSON。",
            )
        if not isinstance(call.arguments, dict):
            return self._failure(call, "invalid_arguments", "MCP 工具参数必须是对象。")

        try:
            remote_result = await asyncio.wait_for(
                self.caller.call_tool(self.remote_name, call.arguments),
                timeout=self.timeout_seconds,
            )
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            return self._failure(
                call,
                "timeout",
                f"MCP 工具执行超过 {self.timeout_seconds:g} 秒。",
            )
        except Exception:
            # 不展示 SDK 原始异常，避免请求头或环境变量进入模型上下文。
            return self._failure(call, "mcp_error", "MCP 工具调用失败，请检查 Server 状态。")

        return self._convert_result(call, remote_result)

    def _convert_result(self, call: ToolCall, result: CallToolResult) -> ToolResult:
        parts: list[str] = []
        unsupported: list[str] = []

        for block in result.content:
            if isinstance(block, TextContent):
                parts.append(block.text)
            else:
                block_type = getattr(block, "type", "unknown")
                unsupported.append(str(block_type))

        if result.structured_content is not None:
            structured = json.dumps(
                result.structured_content,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                default=str,
            )
            parts.append(f"结构化结果：\n{structured}")

        if unsupported:
            unique_types = list(dict.fromkeys(unsupported))
            names = ", ".join(unique_types)
            parts.append(f"[本章暂不支持 MCP 结果类型：{names}]")

        content = "\n\n".join(part for part in parts if part)
        content, truncated = _truncate(content)
        metadata = {"server": self.server_name, "remote_tool": self.remote_name}

        if result.is_error:
            return ToolResult(
                call_id=call.id,
                tool_name=self.name,
                success=False,
                content=content,
                error_code="mcp_remote_error",
                error_message=content or "远端 MCP 工具报告执行失败。",
                metadata=metadata,
                truncated=truncated,
            )

        if unsupported and not any(isinstance(block, TextContent) for block in result.content):
            if result.structured_content is None:
                return ToolResult(
                    call_id=call.id,
                    tool_name=self.name,
                    success=False,
                    content=content,
                    error_code="unsupported_content",
                    error_message=content,
                    metadata=metadata,
                    truncated=truncated,
                )

        return self._success(call, content, metadata=metadata, truncated=truncated)


def adapt_tool(
    server_name: str,
    remote_tool: RemoteTool,
    caller: McpCaller,
) -> McpTool | None:
    """转换远端工具；名称不合法时返回 None 让 Manager 跳过。"""

    full_name = f"mcp__{server_name}__{remote_tool.name}"
    if not VALID_TOOL_NAME.fullmatch(full_name):
        return None

    annotations = remote_tool.annotations
    read_only = bool(annotations and annotations.read_only_hint is True)
    description = remote_tool.description
    if not description:
        description = f"由 MCP Server {server_name} 提供的 {remote_tool.name} 工具。"
    schema = remote_tool.input_schema
    if not isinstance(schema, dict) or not schema:
        schema = {"type": "object"}

    return McpTool(
        name=full_name,
        remote_name=remote_tool.name,
        server_name=server_name,
        description=description,
        input_schema=schema,
        read_only=read_only,
        caller=caller,
    )


def _truncate(content: str) -> tuple[str, bool]:
    if len(content) <= MAX_RESULT_CHARS:
        return content, False
    marker = "\n[truncated]"
    return content[: MAX_RESULT_CHARS - len(marker)] + marker, True
