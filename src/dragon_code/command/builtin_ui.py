"""会改变 TUI 或会话状态的本地命令。"""

from dragon_code.command.ui import CommandUI


async def handle_exit(ui: CommandUI) -> None:
    ui.quit()


async def handle_compact(ui: CommandUI) -> None:
    ui.force_compact()


async def handle_clear(ui: CommandUI) -> None:
    ui.clear_session()


async def handle_plan(ui: CommandUI) -> None:
    ui.enter_plan_mode()


async def handle_resume(ui: CommandUI) -> None:
    ui.open_sessions(resume_only=True)


async def handle_session(ui: CommandUI) -> None:
    ui.open_sessions(resume_only=False)


async def handle_memory(ui: CommandUI) -> None:
    ui.open_memories()


async def handle_permission(ui: CommandUI) -> None:
    ui.open_permissions()
