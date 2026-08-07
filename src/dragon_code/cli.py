"""Dragon Code 命令行入口。"""

import asyncio
import sys
from pathlib import Path

from dragon_code.config import ConfigError, load_config
from dragon_code.mcp import McpManager, load_mcp_config
from dragon_code.tools import create_default_registry
from dragon_code.tui import DragonCodeApp

DEFAULT_CONFIG_PATH = ".dragon-code/config.yaml"


def main() -> None:
    """加载配置并启动终端界面。"""

    try:
        config = load_config(DEFAULT_CONFIG_PATH)
    except ConfigError as error:
        # 启动错误只显示可读信息，不向用户暴露 Python 堆栈。
        print(f"配置错误：{error}", file=sys.stderr)
        raise SystemExit(1) from None

    try:
        asyncio.run(_run_app(config))
    except KeyboardInterrupt:
        # Textual 通常会自行处理 Ctrl+C；这里只做命令行层的最后兜底。
        return


async def _run_app(config) -> None:
    """在同一个事件循环中连接 MCP、运行 TUI 并完成清理。"""

    workdir = Path.cwd()
    registry = create_default_registry(workdir)
    mcp_config = load_mcp_config(Path(DEFAULT_CONFIG_PATH))
    manager = McpManager(mcp_config)

    try:
        await manager.start()
        for warning in manager.warnings():
            print(f"MCP 警告：{warning}", file=sys.stderr)

        for tool in manager.tools():
            try:
                registry.register(tool)
            except ValueError:
                print(f"MCP 警告：工具 {tool.name} 重名，已跳过。", file=sys.stderr)

        app = DragonCodeApp(config, registry)
        await app.run_async()
    finally:
        await manager.close()
