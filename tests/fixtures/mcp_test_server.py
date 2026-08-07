"""ch07 测试使用的真实本地 stdio MCP Server。"""

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

server = MCPServer("dragon-code-test")


@server.tool(
    description="原样返回输入文本，用于验证 Dragon Code 的 MCP 调用链路。",
    annotations=ToolAnnotations(readOnlyHint=True),
)
def echo(text: str) -> str:
    """原样返回文本。"""

    return text


@server.tool(
    description="返回固定的结构化 Dragon Code 测试信息。",
    annotations=ToolAnnotations(readOnlyHint=True),
    structured_output=True,
)
def project_info() -> dict[str, str]:
    """返回固定结构化结果。"""

    return {"project": "Dragon Code", "chapter": "ch07"}


if __name__ == "__main__":
    server.run(transport="stdio")
