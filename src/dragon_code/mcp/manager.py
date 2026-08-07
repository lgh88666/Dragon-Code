"""连接多个 MCP Server，并管理它们的完整生命周期。"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import httpx2
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Tool as RemoteTool

from dragon_code.mcp.config import McpConfig, McpServerConfig
from dragon_code.mcp.tool import McpTool, adapt_tool

CONNECT_TIMEOUT_SECONDS = 30.0
CLOSE_TIMEOUT_SECONDS = 5.0


@dataclass
class _ReadyResult:
    """一个 Server 启动后的工具与警告。"""

    tools: list[McpTool] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    connected: bool = False


@dataclass
class _ServerRuntime:
    """Manager 关闭一个已连接 Server 所需的状态。"""

    name: str
    stop_event: asyncio.Event
    task: asyncio.Task


class McpManager:
    """并发连接、发现工具，并在退出时统一清理。"""

    def __init__(self, config: McpConfig):
        self.config = config
        self._tools: list[McpTool] = []
        self._warnings: list[str] = list(config.warnings)
        self._runtimes: list[_ServerRuntime] = []
        self._started = False
        self._closed = False

    async def start(self) -> None:
        """并发连接所有 Server，最终仍按配置顺序汇总工具。"""

        if self._started:
            return
        self._started = True

        pending = []
        for name, server in self.config.servers.items():
            stop_event = asyncio.Event()
            loop = asyncio.get_running_loop()
            ready: asyncio.Future[_ReadyResult] = loop.create_future()
            task = asyncio.create_task(
                self._run_server(server, stop_event, ready),
                name=f"mcp-server-{name}",
            )
            runtime = _ServerRuntime(name=name, stop_event=stop_event, task=task)
            pending.append((runtime, ready))

        results = await asyncio.gather(
            *(self._wait_until_ready(runtime, ready) for runtime, ready in pending)
        )

        for runtime, result in zip((item[0] for item in pending), results, strict=True):
            self._warnings.extend(result.warnings)
            if result.connected:
                self._runtimes.append(runtime)
                self._tools.extend(result.tools)

    async def close(self) -> None:
        """通知所有生命周期任务退出，并取消超时任务。"""

        if self._closed:
            return
        self._closed = True

        tasks = [runtime.task for runtime in self._runtimes if not runtime.task.done()]
        for runtime in self._runtimes:
            runtime.stop_event.set()
        if not tasks:
            self._runtimes.clear()
            return

        done, pending = await asyncio.wait(tasks, timeout=CLOSE_TIMEOUT_SECONDS)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        if done:
            await asyncio.gather(*done, return_exceptions=True)
        self._runtimes.clear()

    def tools(self) -> list[McpTool]:
        return list(self._tools)

    def warnings(self) -> list[str]:
        return list(self._warnings)

    async def _wait_until_ready(
        self,
        runtime: _ServerRuntime,
        ready: asyncio.Future[_ReadyResult],
    ) -> _ReadyResult:
        try:
            return await asyncio.wait_for(ready, timeout=CONNECT_TIMEOUT_SECONDS)
        except TimeoutError:
            runtime.stop_event.set()
            runtime.task.cancel()
            await asyncio.gather(runtime.task, return_exceptions=True)
            return _ReadyResult(
                warnings=[f"MCP Server {runtime.name} 连接或发现工具超时，已跳过。"]
            )

    async def _run_server(
        self,
        server: McpServerConfig,
        stop_event: asyncio.Event,
        ready: asyncio.Future[_ReadyResult],
    ) -> None:
        """在同一个任务中打开、保持并关闭一个 Server 连接。"""

        try:
            async with self._open_client(server) as client:
                remote_tools = await self._list_all_tools(client)
                tools, warnings = self._adapt_tools(server.name, remote_tools, client)
                if not ready.done():
                    ready.set_result(_ReadyResult(tools=tools, warnings=warnings, connected=True))
                await stop_event.wait()
        except asyncio.CancelledError:
            if not ready.done():
                ready.cancel()
            raise
        except Exception as error:
            if not ready.done():
                ready.set_result(
                    _ReadyResult(
                        warnings=[
                            f"MCP Server {server.name} 连接或发现工具失败"
                            f"（{type(error).__name__}），已跳过。"
                        ]
                    )
                )

    @asynccontextmanager
    async def _open_client(self, server: McpServerConfig) -> AsyncIterator[Client]:
        """按配置创建 v2 Client；测试可以替换这个小入口。"""

        if server.transport == "stdio":
            parameters = StdioServerParameters(
                command=server.command,
                args=server.args,
                env=server.env or None,
            )
            async with Client(stdio_client(parameters)) as client:
                yield client
            return

        timeout = httpx2.Timeout(30.0, read=300.0)
        async with httpx2.AsyncClient(
            headers=server.headers,
            timeout=timeout,
            follow_redirects=True,
        ) as http_client:
            transport = streamable_http_client(server.url, http_client=http_client)
            async with Client(transport) as client:
                yield client

    @staticmethod
    async def _list_all_tools(client: Client) -> list[RemoteTool]:
        tools: list[RemoteTool] = []
        cursor: str | None = None
        while True:
            page = await client.list_tools(cursor=cursor)
            tools.extend(page.tools)
            if page.next_cursor is None:
                return tools
            cursor = page.next_cursor

    @staticmethod
    def _adapt_tools(
        server_name: str,
        remote_tools: list[RemoteTool],
        client: Client,
    ) -> tuple[list[McpTool], list[str]]:
        tools: list[McpTool] = []
        warnings: list[str] = []
        names: set[str] = set()

        for remote_tool in remote_tools:
            tool = adapt_tool(server_name, remote_tool, client)
            if tool is None:
                warnings.append(
                    f"MCP Server {server_name} 的工具 {remote_tool.name} 名称非法，已跳过。"
                )
                continue
            if tool.name in names:
                warnings.append(f"MCP 工具 {tool.name} 重复，已跳过后出现的定义。")
                continue
            names.add(tool.name)
            tools.append(tool)
        return tools, warnings
