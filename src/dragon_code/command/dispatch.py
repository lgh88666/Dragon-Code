"""Slash Command 的解析和异步分发。"""

from dragon_code.command.registry import CommandRegistry
from dragon_code.command.ui import CommandUI


def parse_command(text: str) -> tuple[str, str] | None:
    """返回命令名和原始参数文本；普通文本返回 None。"""

    stripped = text.strip()
    if not stripped.startswith("/"):
        return None
    body = stripped[1:]
    parts = body.split(maxsplit=1)
    if not parts:
        return "", ""
    return parts[0].lower(), parts[1] if len(parts) > 1 else ""


async def dispatch_command(
    text: str,
    registry: CommandRegistry,
    ui: CommandUI,
) -> bool:
    """消费 Slash Command；普通文本返回 False。"""

    parsed = parse_command(text)
    if parsed is None:
        return False

    if not ui.is_idle():
        ui.show_message("当前任务结束或取消后再执行命令。", error=True)
        return True

    name, arguments = parsed
    command = registry.find(name)
    if command is None:
        ui.show_message("未知命令，请输入 /help 查看可用命令。", error=True)
        return True
    if arguments and command.argument_handler is None:
        ui.show_message(f"{command.usage} 不接收参数。", error=True)
        return True

    try:
        if command.argument_handler is not None:
            await command.argument_handler(ui, arguments)
        else:
            await command.handler(ui)
    except Exception as error:
        # 命令错误属于可恢复错误，不允许破坏 Textual 消息循环。
        ui.show_message(f"命令执行失败：{error}", error=True)
    return True
