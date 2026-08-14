"""不调用模型的本地命令。"""

from dragon_code.command.registry import CommandRegistry
from dragon_code.command.ui import CommandStatus, CommandUI


def make_help_handler(registry: CommandRegistry):
    """帮助内容必须始终来自同一个注册中心。"""

    async def handle_help(ui: CommandUI) -> None:
        ui.open_help(registry.visible())

    return handle_help


async def handle_status(ui: CommandUI) -> None:
    ui.show_message(format_status(ui.get_status()))


async def handle_hooks(ui: CommandUI) -> None:
    """只展示安全元信息，不回显命令、Header 或正文。"""

    hooks, issues = ui.hook_items()
    if not hooks and not issues:
        ui.show_message("当前没有加载任何 Hook。")
        return
    lines = ["已加载 Hook"]
    for hook in hooks:
        lines.append(
            f"- {hook.name} · {hook.event.value} · {hook.action.type.value} · "
            f"{hook.source} · once={str(hook.only_once).lower()} · "
            f"async={str(hook.run_async).lower()}"
        )
    if issues:
        lines.append("配置问题")
        for issue in issues:
            name = issue.hook_name or "文件"
            lines.append(f"- {name}：{issue.message}")
    ui.show_message("\n".join(lines))


def format_status(status: CommandStatus) -> str:
    """把状态快照转换成适合终端阅读的文本。"""

    input_tokens = _number_or_unknown(status.input_tokens)
    output_tokens = _number_or_unknown(status.output_tokens)
    return "\n".join(
        [
            "Dragon Code 状态",
            f"版本：{status.version}",
            f"工作目录：{status.cwd}",
            f"Provider：{status.provider}",
            f"模型：{status.model}",
            f"权限模式：{status.permission_mode}",
            f"会话 ID：{status.session_id}",
            f"Token：输入 {input_tokens} / 输出 {output_tokens}",
            f"缓存：写入 {status.cache_write_tokens} / 读取 {status.cache_read_tokens}",
            f"上下文估算：{status.estimated_context_tokens}",
            f"工具：内置 {status.builtin_tool_count} / MCP {status.mcp_tool_count}",
            f"记忆：用户 {status.user_memory_count} / 项目 {status.project_memory_count}",
        ]
    )


def _number_or_unknown(value: int | None) -> str:
    return "未知" if value is None else str(value)
