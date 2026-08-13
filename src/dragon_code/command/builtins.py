"""集中注册 Dragon Code 的 12 条内置命令。"""

from dragon_code.command.builtin_local import handle_status, make_help_handler
from dragon_code.command.builtin_prompt import handle_do, handle_review
from dragon_code.command.builtin_ui import (
    handle_clear,
    handle_compact,
    handle_exit,
    handle_memory,
    handle_permission,
    handle_plan,
    handle_resume,
    handle_session,
)
from dragon_code.command.command import Command, CommandKind
from dragon_code.command.registry import CommandRegistry


def create_command_registry() -> CommandRegistry:
    """创建固定内置命令；本章不支持运行时增删。"""

    registry = CommandRegistry()
    commands = [
        Command(
            "exit",
            ("q", "quit"),
            "安全退出 Dragon Code",
            "/exit",
            CommandKind.LOCAL_UI,
            handle_exit,
        ),
        Command(
            "plan",
            ("p",),
            "进入只读 Plan Mode",
            "/plan",
            CommandKind.LOCAL_UI,
            handle_plan,
        ),
        Command(
            "do",
            ("d",),
            "执行已经完成的计划",
            "/do",
            CommandKind.PROMPT,
            handle_do,
        ),
        Command(
            "compact",
            ("cp",),
            "立即压缩当前对话上下文",
            "/compact",
            CommandKind.LOCAL_UI,
            handle_compact,
        ),
        Command(
            "resume",
            (),
            "搜索并恢复历史会话",
            "/resume",
            CommandKind.LOCAL_UI,
            handle_resume,
        ),
        Command(
            "clear",
            ("cl",),
            "开始一个新的空白会话",
            "/clear",
            CommandKind.LOCAL_UI,
            handle_clear,
        ),
        Command(
            "status",
            ("s",),
            "显示当前综合状态",
            "/status",
            CommandKind.LOCAL,
            handle_status,
        ),
        Command(
            "memory",
            ("mem",),
            "查看和管理长期记忆",
            "/memory",
            CommandKind.LOCAL_UI,
            handle_memory,
        ),
        Command(
            "permission",
            ("perm",),
            "查看并切换运行时权限模式",
            "/permission",
            CommandKind.LOCAL_UI,
            handle_permission,
        ),
        Command(
            "session",
            ("ss",),
            "查看和管理当前项目会话",
            "/session",
            CommandKind.LOCAL_UI,
            handle_session,
        ),
        Command(
            "review",
            ("r",),
            "以只读方式审查代码",
            "/review",
            CommandKind.PROMPT,
            handle_review,
        ),
    ]
    for command in commands:
        registry.register(command)

    # help 需要读取最终注册中心，因此最后创建，但 visible() 会稳定排序。
    registry.register(
        Command(
            "help",
            ("h", "?"),
            "显示命令列表和详细说明",
            "/help",
            CommandKind.LOCAL,
            make_help_handler(registry),
        )
    )
    return registry
