"""命令行入口的 MCP 装配和清理测试。"""

import pytest

from dragon_code import cli
from dragon_code.mcp.config import McpConfig
from dragon_code.models import AppConfig, ProviderConfig


@pytest.mark.asyncio
async def test_run_app_starts_mcp_before_tui_and_always_closes(monkeypatch):
    events: list[str] = []

    class FakeManager:
        def __init__(self, config):
            assert isinstance(config, McpConfig)

        async def start(self):
            events.append("manager-start")

        def warnings(self):
            return []

        def tools(self):
            return []

        async def close(self):
            events.append("manager-close")

    class FakeApp:
        def __init__(self, config, registry, **services):
            assert registry is not None
            assert services["session_manager"] is not None
            assert services["memory_manager"] is not None
            events.append("app-create")

        async def run_async(self):
            events.append("app-run")

    monkeypatch.setattr(cli, "load_mcp_config", lambda _path: McpConfig())
    monkeypatch.setattr(cli, "McpManager", FakeManager)
    monkeypatch.setattr(cli, "DragonCodeApp", FakeApp)

    config = AppConfig([ProviderConfig("Fake", "openai", "fake-key", "fake-model")])
    await cli._run_app(config)

    assert events == [
        "manager-start",
        "app-create",
        "app-run",
        "manager-close",
    ]


@pytest.mark.asyncio
async def test_run_app_closes_mcp_when_tui_fails(monkeypatch):
    closed = False

    class FakeManager:
        def __init__(self, config):
            pass

        async def start(self):
            pass

        def warnings(self):
            return []

        def tools(self):
            return []

        async def close(self):
            nonlocal closed
            closed = True

    class BrokenApp:
        def __init__(self, config, registry, **services):
            assert services["custom_instructions"] == ""

        async def run_async(self):
            raise RuntimeError("TUI failed")

    monkeypatch.setattr(cli, "load_mcp_config", lambda _path: McpConfig())
    monkeypatch.setattr(cli, "McpManager", FakeManager)
    monkeypatch.setattr(cli, "DragonCodeApp", BrokenApp)

    config = AppConfig([ProviderConfig("Fake", "openai", "fake-key", "fake-model")])
    with pytest.raises(RuntimeError, match="TUI failed"):
        await cli._run_app(config)

    assert closed is True
