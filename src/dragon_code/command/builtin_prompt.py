"""会把预设任务送入 Agent Loop 的命令。"""

from dragon_code.command.ui import CommandUI


async def handle_do(ui: CommandUI) -> None:
    ui.execute_plan()


async def handle_review(ui: CommandUI) -> None:
    ui.open_review()


def build_review_prompt(target: str) -> str:
    """构造稳定、只报告问题的审查任务。"""

    return (
        f"请对以下目标进行只读代码审查：{target}\n\n"
        "重点检查：\n"
        "1. 功能错误和边界情况；\n"
        "2. 安全问题；\n"
        "3. 异步任务、文件和子进程是否正确清理；\n"
        "4. 对现有功能的回归风险；\n"
        "5. 缺失或不足的测试。\n\n"
        "只报告发现的问题，按严重程度排序并标明文件位置。不要修改任何文件。"
    )
