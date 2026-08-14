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

    def names(self) -> list[str]:
        return list(self._tools)

    def definitions(self) -> list[ToolDefinition]:
        return [tool.definition() for tool in self._tools.values()]

    def counts(self) -> tuple[int, int]:
        """返回内置工具数和 MCP 工具数。"""

        mcp_count = sum(1 for name in self._tools if name.startswith("mcp__"))
        skill_count = sum(1 for name in self._tools if name.startswith("skill__"))
        system_count = sum(1 for tool in self._tools.values() if tool.is_system_tool)
        return len(self._tools) - mcp_count - skill_count - system_count, mcp_count

    def skill_count(self) -> int:
        return sum(1 for name in self._tools if name.startswith("skill__"))

    def subset(self, names: set[str]) -> "ToolRegistry":
        """按原注册顺序返回共享工具实例的子注册中心。"""

        registry = ToolRegistry()
        for name, tool in self._tools.items():
            if name in names:
                registry.register(tool)
        return registry

    def restricted(self, names: set[str]) -> "ToolRegistry":
        """保留白名单工具，同时始终带上系统工具。"""

        registry = ToolRegistry()
        for name, tool in self._tools.items():
            if name in names or tool.is_system_tool:
                registry.register(tool)
        return registry

    def combined(self, *others: "ToolRegistry") -> "ToolRegistry":
        """按原顺序合并多个注册中心，不修改任何输入。"""

        registry = ToolRegistry()
        for source in (self, *others):
            for tool in source._tools.values():
                registry.register(tool)
        return registry

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


def create_default_registry(
    workdir: Path,
    extra_read_roots: list[Path] | None = None,
) -> ToolRegistry:
    """为一次 Dragon Code 会话注册固定的六个工具。"""

    registry = ToolRegistry()
    for tool in [
        ReadTool(workdir, extra_read_roots),
        WriteTool(workdir),
        EditTool(workdir),
        BashTool(workdir),
        GlobTool(workdir),
        GrepTool(workdir),
    ]:
        registry.register(tool)
    return registry
