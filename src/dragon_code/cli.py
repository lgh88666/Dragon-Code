"""Dragon Code 命令行入口。"""

import asyncio
import sys
from pathlib import Path

from dragon_code.command import create_command_registry
from dragon_code.config import ConfigError, load_config
from dragon_code.instructions import InstructionLoader
from dragon_code.mcp import McpManager, load_mcp_config
from dragon_code.memory import MemoryManager
from dragon_code.sessions import SessionManager
from dragon_code.skills import SkillLoader, SkillManager
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
    instruction_loader = InstructionLoader(workdir)
    custom_instructions = instruction_loader.load()
    for warning in instruction_loader.warnings():
        print(f"项目指令警告：{warning}", file=sys.stderr)

    memory_manager = MemoryManager(workdir)
    memory_manager.load_indexes()
    session_manager = SessionManager(workdir)
    cleanup_task = asyncio.create_task(asyncio.to_thread(session_manager.cleanup_expired, 45))
    registry = create_default_registry(workdir, [memory_manager.user_memory_dir])
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

        commands = create_command_registry().visible()
        reserved_commands = {
            name for command in commands for name in (command.name, *command.aliases)
        }
        skill_manager = SkillManager(
            SkillLoader(
                workdir,
                reserved_commands=reserved_commands,
                base_tool_names=set(registry.names()) | {"LoadSkill"},
            )
        )
        skill_manager.reload()
        for issue in skill_manager.issues():
            print(f"Skill 警告：{issue.message}", file=sys.stderr)

        app = DragonCodeApp(
            config,
            registry,
            session_manager=session_manager,
            memory_manager=memory_manager,
            custom_instructions=custom_instructions,
            skill_manager=skill_manager,
        )
        await app.run_async()
    finally:
        session_manager.close()
        await memory_manager.close()
        if not cleanup_task.done():
            cleanup_task.cancel()
        await asyncio.gather(cleanup_task, return_exceptions=True)
        await manager.close()
