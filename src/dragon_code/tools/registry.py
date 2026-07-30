"""工具注册、查找和默认六工具组装。"""

from pathlib import Path

from dragon_code.models import ToolCall, ToolDefinition, ToolResult
from dragon_code.tools.base import Tool
from dragon_code.tools.bash import BashTool
from dragon_code.tools.file_tools import EditTool, ReadTool, WriteTool
from dragon_code.tools.search_tools import GlobTool, GrepTool


class ToolRegistry:
    """集中保存当前会话可用的全部工具。"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"工具名重复：{tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def definitions(self) -> list[ToolDefinition]:
        return [tool.definition() for tool in self._tools.values()]

    async def execute(self, call: ToolCall) -> ToolResult:
        tool = self.get(call.name)
        if tool is None:
            return ToolResult(
                call_id=call.id,
                tool_name=call.name,
                success=False,
                error_code="unknown_tool",
                error_message=f"未注册工具：{call.name}",
            )
        return await tool.execute(call)


def create_default_registry(workdir: Path) -> ToolRegistry:
    """为一次 Dragon Code 会话注册固定的六个工具。"""

    registry = ToolRegistry()
    for tool in [
        ReadTool(workdir),
        WriteTool(workdir),
        EditTool(workdir),
        BashTool(workdir),
        GlobTool(workdir),
        GrepTool(workdir),
    ]:
        registry.register(tool)
    return registry
