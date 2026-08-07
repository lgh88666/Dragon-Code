"""MCP Manager 的并发、分页、隔离和关闭测试。"""

import asyncio
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from dragon_code.mcp.config import McpConfig, McpServerConfig
from dragon_code.mcp.manager import McpManager
from dragon_code.models import ToolCall


class FakeClient:
    def __init__(
        self,
        pages: list[ListToolsResult],
        *,
        delay: float = 0,
    ):
        self.pages = pages
        self.delay = delay
        self.list_calls: list[str | None] = []
        self.call_count = 0

    async def list_tools(self, *, cursor=None):
        await asyncio.sleep(self.delay)
        self.list_calls.append(cursor)
        page = self.pages[self.call_count]
        self.call_count += 1
        return page

    async def call_tool(self, name: str, arguments: dict):
        return CallToolResult(content=[TextContent(text=f"{name}:{arguments}")])


def tool(name: str) -> Tool:
    return Tool(name=name, description=f"{name} tool", inputSchema={"type": "object"})


def server(name: str) -> McpServerConfig:
    return McpServerConfig(name=name, transport="stdio", command="fake")


def one_page(*names: str) -> list[ListToolsResult]:
    return [ListToolsResult(tools=[tool(name) for name in names])]


def install_fake_clients(
    monkeypatch: pytest.MonkeyPatch,
    manager: McpManager,
    clients: dict[str, FakeClient | Exception],
    exits: list[str] | None = None,
):
    @asynccontextmanager
    async def fake_open(config: McpServerConfig):
        value = clients[config.name]
        if isinstance(value, Exception):
            raise value
        try:
            yield value
        finally:
            if exits is not None:
                exits.append(config.name)

    monkeypatch.setattr(manager, "_open_client", fake_open)


@pytest.mark.asyncio
async def test_manager_lists_all_pages_and_closes(monkeypatch: pytest.MonkeyPatch):
    pages = [
        ListToolsResult(tools=[tool("one")], nextCursor="next"),
        ListToolsResult(tools=[tool("two")]),
    ]
    manager = McpManager(McpConfig(servers={"alpha": server("alpha")}))
    exits: list[str] = []
    fake = FakeClient(pages)
    install_fake_clients(monkeypatch, manager, {"alpha": fake}, exits)

    await manager.start()

    assert [item.name for item in manager.tools()] == ["mcp__alpha__one", "mcp__alpha__two"]
    assert fake.list_calls == [None, "next"]
    assert exits == []

    await manager.close()
    assert exits == ["alpha"]


@pytest.mark.asyncio
async def test_manager_connects_concurrently_but_keeps_config_order(
    monkeypatch: pytest.MonkeyPatch,
):
    config = McpConfig(
        servers={
            "slow": server("slow"),
            "fast": server("fast"),
        }
    )
    manager = McpManager(config)
    install_fake_clients(
        monkeypatch,
        manager,
        {
            "slow": FakeClient(one_page("slow-tool"), delay=0.05),
            "fast": FakeClient(one_page("fast-tool"), delay=0.01),
        },
    )

    started = time.monotonic()
    await manager.start()
    elapsed = time.monotonic() - started

    assert elapsed < 0.09
    assert [item.name for item in manager.tools()] == [
        "mcp__slow__slow-tool",
        "mcp__fast__fast-tool",
    ]
    await manager.close()


@pytest.mark.asyncio
async def test_manager_isolates_failed_server(monkeypatch: pytest.MonkeyPatch):
    config = McpConfig(
        servers={
            "broken": server("broken"),
            "healthy": server("healthy"),
        }
    )
    manager = McpManager(config)
    install_fake_clients(
        monkeypatch,
        manager,
        {
            "broken": RuntimeError("Authorization secret"),
            "healthy": FakeClient(one_page("echo")),
        },
    )

    await manager.start()

    assert [item.name for item in manager.tools()] == ["mcp__healthy__echo"]
    assert "broken" in manager.warnings()[0]
    assert "secret" not in manager.warnings()[0]
    await manager.close()


@pytest.mark.asyncio
async def test_manager_times_out_one_server(monkeypatch: pytest.MonkeyPatch):
    manager = McpManager(McpConfig(servers={"slow": server("slow")}))

    @asynccontextmanager
    async def never_opens(config: McpServerConfig):
        await asyncio.Event().wait()
        yield FakeClient(one_page("unused"))

    monkeypatch.setattr(manager, "_open_client", never_opens)
    monkeypatch.setattr("dragon_code.mcp.manager.CONNECT_TIMEOUT_SECONDS", 0.01)

    await manager.start()

    assert manager.tools() == []
    assert "超时" in manager.warnings()[0]
    await manager.close()


@pytest.mark.asyncio
async def test_manager_skips_illegal_and_duplicate_tools(monkeypatch: pytest.MonkeyPatch):
    manager = McpManager(McpConfig(servers={"alpha": server("alpha")}))
    fake = FakeClient(one_page("bad.name", "echo", "echo"))
    install_fake_clients(monkeypatch, manager, {"alpha": fake})

    await manager.start()

    assert [item.name for item in manager.tools()] == ["mcp__alpha__echo"]
    assert len(manager.warnings()) == 2
    await manager.close()


@pytest.mark.asyncio
async def test_manager_close_cancels_slow_exit(monkeypatch: pytest.MonkeyPatch):
    manager = McpManager(McpConfig(servers={"slow": server("slow")}))
    exit_started = asyncio.Event()

    @asynccontextmanager
    async def slow_exit(config: McpServerConfig):
        try:
            yield FakeClient(one_page("echo"))
        finally:
            exit_started.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(manager, "_open_client", slow_exit)
    monkeypatch.setattr("dragon_code.mcp.manager.CLOSE_TIMEOUT_SECONDS", 0.01)

    await manager.start()
    await manager.close()

    assert exit_started.is_set()
    assert manager._runtimes == []
    await manager.close()


@pytest.mark.asyncio
async def test_manager_start_is_idempotent(monkeypatch: pytest.MonkeyPatch):
    manager = McpManager(McpConfig(servers={"alpha": server("alpha")}))
    fake = FakeClient(one_page("echo"))
    install_fake_clients(monkeypatch, manager, {"alpha": fake})

    await manager.start()
    await manager.start()

    assert fake.call_count == 1
    await manager.close()


@pytest.mark.asyncio
async def test_http_transport_receives_url_and_headers(monkeypatch: pytest.MonkeyPatch):
    """HTTP 配置必须原样交给 SDK 传输层，不能在中途丢失请求头。"""

    captured: dict[str, object] = {}

    class FakeHttpClient:
        def __init__(self, **kwargs):
            captured["http_options"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    class FakeSdkClient:
        def __init__(self, transport):
            captured["transport"] = transport

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    def fake_transport(url: str, *, http_client):
        captured["url"] = url
        captured["http_client"] = http_client
        return "fake-http-transport"

    monkeypatch.setattr("dragon_code.mcp.manager.httpx2.AsyncClient", FakeHttpClient)
    monkeypatch.setattr("dragon_code.mcp.manager.streamable_http_client", fake_transport)
    monkeypatch.setattr("dragon_code.mcp.manager.Client", FakeSdkClient)

    config = McpServerConfig(
        name="remote",
        transport="http",
        url="https://mcp.example.test/api",
        headers={"Authorization": "Bearer test-token"},
    )
    manager = McpManager(McpConfig(servers={"remote": config}))

    async with manager._open_client(config):
        pass

    assert captured["url"] == "https://mcp.example.test/api"
    assert captured["http_options"]["headers"] == {"Authorization": "Bearer test-token"}
    assert captured["transport"] == "fake-http-transport"


@pytest.mark.asyncio
async def test_real_stdio_server_discovery_call_and_close():
    fixture = Path(__file__).parent / "fixtures" / "mcp_test_server.py"
    config = McpConfig(
        servers={
            "local_test": McpServerConfig(
                name="local_test",
                transport="stdio",
                command=sys.executable,
                args=[str(fixture)],
            )
        }
    )
    manager = McpManager(config)

    await manager.start()
    try:
        assert manager.warnings() == []
        tools = {item.name: item for item in manager.tools()}
        assert set(tools) == {
            "mcp__local_test__echo",
            "mcp__local_test__project_info",
        }

        result = await tools["mcp__local_test__echo"].execute(
            ToolCall(
                id="real-stdio",
                name="mcp__local_test__echo",
                arguments={"text": "dragon"},
            )
        )
        assert result.success is True
        assert "dragon" in result.content
    finally:
        await manager.close()

    assert manager._runtimes == []
