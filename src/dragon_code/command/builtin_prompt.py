"""会把预设任务送入 Agent Loop 的命令。"""

from dragon_code.command.ui import CommandUI


async def handle_do(ui: CommandUI) -> None:
    ui.execute_plan()


async def handle_review(ui: CommandUI) -> None:
    ui.open_review()
