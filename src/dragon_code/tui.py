"""Dragon Code 的 Textual 终端界面。"""

import os
import time
from collections.abc import Callable
from enum import Enum
from pathlib import Path

from rich.console import Group
from rich.markdown import Markdown
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.selection import Selection
from textual.strip import Strip
from textual.timer import Timer
from textual.widgets import OptionList, RichLog, Static, TextArea
from textual.worker import Worker

from dragon_code import __version__
from dragon_code.agent import Agent
from dragon_code.models import (
    AppConfig,
    ProviderConfig,
    TokenUsage,
    ToolCall,
    ToolResult,
)
from dragon_code.prompt import DO_PLAN_PROMPT, build_system_prompt, render_banner
from dragon_code.providers.base import BaseProvider, ProviderError
from dragon_code.providers.factory import create_provider
from dragon_code.session import Conversation
from dragon_code.tools import create_default_registry


def format_tool_call(call: ToolCall) -> str:
    """生成 Claude Code 风格的单行工具说明。"""

    arguments = call.arguments or {}
    if call.name in {"Read", "Write", "Edit"}:
        key = arguments.get("path", "")
    elif call.name == "Bash":
        key = arguments.get("command", "")
    elif call.name == "Glob":
        key = arguments.get("pattern", "")
    elif call.name == "Grep":
        key = f"{arguments.get('pattern', '')}, {arguments.get('path', '.')}"
    else:
        key = ""
    key = str(key).replace("\n", " ")
    if len(key) > 100:
        key = key[:97] + "..."
    return f"● {call.name}({key})"


def format_tool_result(result: ToolResult) -> str:
    """只为 TUI 生成短摘要，完整内容仍只回灌给模型。"""

    if result.success:
        text = result.content or "执行成功"
    else:
        text = result.error_message or "执行失败"
    text = text.replace("\n", " ")
    if len(text) > 240:
        text = text[:237] + "..."
    if result.truncated:
        text += "（结果已截断）"
    return text


class SessionState(Enum):
    """当前终端会话所处的状态。"""

    SELECTING = "selecting"
    IDLE = "idle"
    STREAMING = "streaming"


class ConversationLog(RichLog):
    """让 RichLog 已渲染的聊天行可以被 Textual 正确复制。"""

    def render_line(self, y: int) -> Strip:
        """给渲染行附加文字位置，并高亮当前选择。"""

        scroll_x, scroll_y = self.scroll_offset
        line = super().render_line(y)
        selection = self.text_selection

        if selection is not None:
            span = selection.get_span(scroll_y + y)
            if span is not None:
                start, end = span
                rich_text = Text()
                for segment in line:
                    rich_text.append(segment.text, style=segment.style)
                if end == -1:
                    end = len(rich_text)
                selection_style = self.screen.get_component_rich_style("screen--selection")
                rich_text.stylize(selection_style, start, end)
                line = Strip(rich_text.render(self.app.console), line.cell_length)

        # Textual 依靠这些位置元信息，把鼠标坐标换算成文字下标。
        return line.apply_offsets(scroll_x, scroll_y + y)

    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        """根据鼠标选择范围提取聊天区中的纯文本。"""

        if not self.lines:
            return None

        text = "\n".join(line.text.rstrip() for line in self.lines)
        return selection.extract(text), "\n"


class MessageInput(TextArea):
    """支持 Enter 提交、Alt+Enter 换行的输入框。"""

    BINDINGS = [
        Binding("enter", "submit", show=False, priority=True),
        Binding("alt+enter", "insert_newline", show=False, priority=True),
    ]

    class Submitted(Message):
        """用户按 Enter 后发送给 DragonCodeApp 的消息。"""

        def __init__(self, value: str):
            super().__init__()
            self.value = value

    def action_submit(self) -> None:
        """提交完整输入，不在这里修改应用状态。"""

        self.post_message(self.Submitted(self.text))

    def action_insert_newline(self) -> None:
        """在当前光标位置插入换行。"""

        self.insert("\n")


class ProviderSelectScreen(ModalScreen[int]):
    """多个 Provider 时显示的方向键选择界面。"""

    def __init__(self, providers: list[ProviderConfig]):
        super().__init__()
        self.providers = providers

    def compose(self) -> ComposeResult:
        options = [f"{provider.name}  ·  {provider.model}" for provider in self.providers]
        with Vertical(id="provider-dialog"):
            yield Static("选择本次会话使用的 Provider", id="provider-title")
            yield OptionList(*options, id="provider-options")

    def on_mount(self) -> None:
        self.query_one("#provider-options", OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option_index)


class DragonCodeApp(App):
    """Dragon Code 主界面。"""

    CSS_PATH = "dragon_code.tcss"
    BINDINGS = [
        Binding("ctrl+c", "copy_or_quit", show=False, priority=True),
        Binding("escape", "cancel_turn", show=False, priority=True),
    ]

    def __init__(
        self,
        config: AppConfig,
        provider_factory: Callable[[ProviderConfig], BaseProvider] = create_provider,
    ):
        super().__init__()
        self.config = config
        self.provider_factory = provider_factory
        self.session_state = SessionState.SELECTING
        self.provider: BaseProvider | None = None
        self.agent: Agent | None = None
        self.reply_buffer = ""
        self.turn_start = 0.0
        self.timer: Timer | None = None
        self.stream_worker: Worker | None = None
        self.spinner_index = 0
        self.current_iteration = 0
        self.max_iterations = 0
        self.task_usage = TokenUsage(0, 0)
        self.session_usage = TokenUsage(0, 0)
        self.task_usage_committed = False

    def compose(self) -> ComposeResult:
        yield Static(render_banner(__version__, os.getcwd()), id="banner")
        yield Static("● 对话服务已就绪", id="ready")
        yield ConversationLog(id="conversation", wrap=True, highlight=False, markup=False)
        yield Static("", id="streaming", markup=False)
        yield Static("", id="timer", markup=False)
        with Horizontal(id="input-row"):
            yield Static("❯", id="input-prompt")
            yield MessageInput(
                id="message-input",
                placeholder="Send a message...",
                show_line_numbers=False,
                soft_wrap=True,
            )
        with Horizontal(id="statusbar"):
            yield Static("", id="provider-name")
            yield Static("Token 0", id="token-usage")
            yield Static("", id="model-name")

    def on_mount(self) -> None:
        if len(self.config.providers) == 1:
            self._activate_provider(0)
            return

        self.session_state = SessionState.SELECTING
        self.push_screen(
            ProviderSelectScreen(self.config.providers),
            callback=self._provider_selected,
        )

    def _provider_selected(self, selected_index: int | None) -> None:
        """选择完成后创建本次会话使用的 Provider。"""

        if selected_index is None:
            self.action_safe_quit()
            return
        self._activate_provider(selected_index)

    def _activate_provider(self, index: int) -> None:
        config = self.config.providers[index]
        self.provider = self.provider_factory(config)
        workdir = Path.cwd()
        self.agent = Agent(
            self.provider,
            Conversation(),
            build_system_prompt(workdir),
            create_default_registry(workdir),
        )
        self.session_state = SessionState.IDLE
        self.query_one("#provider-name", Static).update(self.provider.name)
        self.query_one("#model-name", Static).update(self.provider.model)
        self.query_one("#message-input", MessageInput).focus()

    def on_message_input_submitted(self, event: MessageInput.Submitted) -> None:
        """接收输入框提交事件。"""

        if self.session_state is not SessionState.IDLE:
            return

        text = event.value
        if not text.strip():
            return
        if text.strip() == "/exit":
            self.action_safe_quit()
            return

        command = text.strip()
        if command == "/plan":
            self._enter_plan_mode()
            return
        if command.startswith("/plan "):
            task = command[len("/plan ") :].strip()
            if task:
                self._enter_plan_mode(show_notice=False)
                self._start_turn(task, display_text=text)
            return
        if command == "/do":
            self._execute_plan()
            return

        self._start_turn(text)

    def _start_turn(self, user_text: str, display_text: str | None = None) -> None:
        """更新界面状态并启动异步模型请求。"""

        conversation = self.query_one("#conversation", RichLog)
        visible_text = display_text if display_text is not None else user_text
        conversation.write(Text(f"❯ {visible_text}", style="bold cyan"))

        input_widget = self.query_one("#message-input", MessageInput)
        input_widget.load_text("")
        input_widget.disabled = True

        self.reply_buffer = ""
        self.turn_start = time.monotonic()
        self.spinner_index = 0
        self.current_iteration = 0
        self.max_iterations = 0
        self.task_usage = TokenUsage(0, 0)
        self.task_usage_committed = False
        self.session_state = SessionState.STREAMING
        self.query_one("#streaming", Static).update("")
        self._update_timer()
        self.timer = self.set_interval(0.1, self._update_timer)
        self.stream_worker = self.run_worker(
            self._consume_turn(user_text),
            name="llm-stream",
            exclusive=True,
            exit_on_error=False,
        )

    async def _consume_turn(self, user_text: str) -> None:
        """消费 Agent 事件并实时更新界面。"""

        if self.agent is None:
            self._finish_with_error(ProviderError("unknown", "当前没有可用的 Provider。"))
            return

        async for event in self.agent.run(user_text):
            if event.type == "progress":
                self.current_iteration = event.iteration
                self.max_iterations = event.max_iterations
                self._update_timer()
            elif event.type == "text":
                self.reply_buffer += event.text
                self.query_one("#streaming", Static).update(self.reply_buffer)
            elif event.type == "tool_start" and event.tool_call is not None:
                self._flush_streaming_text()
                line = Text(format_tool_call(event.tool_call), style="bold cyan")
                self.query_one("#conversation", RichLog).write(line)
            elif event.type == "tool_end" and event.tool_result is not None:
                self._write_tool_result(event.tool_result)
            elif event.type == "usage" and event.usage is not None:
                self.task_usage = event.usage
                self._update_usage_status(event.usage, task_in_progress=True)
            elif event.type == "completed":
                self._finish_with_reply(event.text, event.usage)
            elif event.type == "cancelled":
                self._finish_with_status(event.text, "bold yellow", event.usage)
            elif event.type == "limit":
                self._finish_with_status(event.text, "bold yellow", event.usage)
            elif event.type == "error":
                error = event.error
                if isinstance(error, ProviderError):
                    self._finish_with_error(error, event.usage)
                else:
                    self._finish_with_error(
                        ProviderError("unknown", "模型请求失败，请稍后再试。"),
                        event.usage,
                    )

    def _write_tool_result(self, result: ToolResult) -> None:
        """按结果类型显示成功、错误、取消或状态未知。"""

        if result.success:
            style = "green"
            prefix = "  └─ "
        elif result.error_code == "cancelled":
            style = "bold yellow"
            prefix = "  └─ 已取消："
        elif result.error_code == "cancel_outcome_unknown":
            style = "bold yellow"
            prefix = "  └─ 状态未知："
        else:
            style = "bold red"
            prefix = "  └─ 错误："
        line = Text(prefix + format_tool_result(result), style=style)
        self.query_one("#conversation", RichLog).write(line)

    def _flush_streaming_text(self) -> None:
        """把工具调用前的模型文字固定到历史区。"""

        if not self.reply_buffer:
            return
        self.query_one("#conversation", RichLog).write(Markdown(self.reply_buffer))
        self.reply_buffer = ""
        self.query_one("#streaming", Static).update("")

    def _update_timer(self) -> None:
        """刷新等待动画和已用秒数。"""

        if self.session_state is not SessionState.STREAMING:
            return

        frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        frame = frames[self.spinner_index % len(frames)]
        self.spinner_index += 1
        elapsed = int(time.monotonic() - self.turn_start)
        progress = ""
        if self.current_iteration:
            progress = f" · 第 {self.current_iteration}/{self.max_iterations} 轮"
        self.query_one("#timer", Static).update(f"{frame} Imagining…{progress} ({elapsed}s)")

    def _stop_turn(self) -> float:
        """停止计时并恢复输入，返回本轮总耗时。"""

        elapsed = time.monotonic() - self.turn_start
        if self.timer is not None:
            self.timer.stop()
            self.timer = None

        self.stream_worker = None
        self.session_state = SessionState.IDLE
        self.query_one("#streaming", Static).update("")
        self.query_one("#timer", Static).update("")

        input_widget = self.query_one("#message-input", MessageInput)
        input_widget.disabled = False
        input_widget.focus()
        return elapsed

    def _finish_with_reply(self, reply: str, usage: TokenUsage | None = None) -> None:
        """把完整回复定型为 Markdown 并写入历史区。"""

        self._commit_task_usage(usage)
        elapsed = self._stop_turn()
        rendered = Group(
            Markdown(reply),
            Text(
                f"完成 · {elapsed:.1f}s · {self._format_usage(self.task_usage)}",
                style="dim",
            ),
        )
        self.query_one("#conversation", RichLog).write(rendered)

    def _finish_with_error(
        self,
        error: ProviderError,
        usage: TokenUsage | None = None,
    ) -> None:
        """显示脱敏错误并允许用户继续对话。"""

        self._flush_streaming_text()
        self._commit_task_usage(usage)
        self._stop_turn()
        message = Text(f"● {error.message}", style="bold red")
        self.query_one("#conversation", RichLog).write(message)

    def _finish_with_status(
        self,
        message: str,
        style: str,
        usage: TokenUsage | None = None,
    ) -> None:
        """显示取消或安全上限提示，并恢复输入状态。"""

        self._flush_streaming_text()
        self._commit_task_usage(usage)
        self._stop_turn()
        self.query_one("#conversation", RichLog).write(Text(f"● {message}", style=style))

    def _commit_task_usage(self, usage: TokenUsage | None) -> None:
        """一个任务只向会话累计一次 Token 用量。"""

        if usage is not None:
            self.task_usage = usage
        if not self.task_usage_committed:
            self.session_usage = self.session_usage.add(self.task_usage)
            self.task_usage_committed = True
        self._update_usage_status(self.session_usage)

    def _update_usage_status(
        self,
        usage: TokenUsage,
        *,
        task_in_progress: bool = False,
    ) -> None:
        prefix = "本轮" if task_in_progress else "会话"
        self.query_one("#token-usage", Static).update(f"{prefix} {self._format_usage(usage)}")

    @staticmethod
    def _format_usage(usage: TokenUsage) -> str:
        if usage.input_tokens is None or usage.output_tokens is None:
            return "Token 用量未知"
        return (
            f"Token {usage.total_tokens} (输入 {usage.input_tokens} / 输出 {usage.output_tokens})"
        )

    def _enter_plan_mode(self, *, show_notice: bool = True) -> None:
        """进入持续只读的 Plan Mode。"""

        if self.agent is None:
            return
        self.agent.enter_plan_mode()
        self.query_one("#ready", Static).update("● Plan Mode：仅使用只读工具")
        self._clear_input()
        if show_notice:
            self.query_one("#conversation", RichLog).write(
                Text("● 已进入 Plan Mode。输入任务开始规划，输入 /do 执行计划。", style="cyan")
            )

    def _execute_plan(self) -> None:
        """离开 Plan Mode，并让 Agent 立即执行已经完成的计划。"""

        if self.agent is None or not self.agent.can_execute_plan():
            self._clear_input()
            self.query_one("#conversation", RichLog).write(
                Text("● 当前没有可执行的计划，请先使用 /plan 完成规划。", style="bold yellow")
            )
            return

        self.agent.enter_default_mode()
        self.query_one("#ready", Static).update("● 对话服务已就绪")
        self._start_turn(DO_PLAN_PROMPT, display_text="/do")

    def _clear_input(self) -> None:
        self.query_one("#message-input", MessageInput).load_text("")

    def action_safe_quit(self) -> None:
        """清理计时器和 Worker 后退出。"""

        if self.timer is not None:
            self.timer.stop()
            self.timer = None
        if self.agent is not None:
            self.agent.request_cancel()
        if self.stream_worker is not None:
            self.stream_worker.cancel()
            self.stream_worker = None
        self.exit()

    def action_cancel_turn(self) -> None:
        """Esc 只取消正在运行的 Agent，不退出应用。"""

        if self.session_state is SessionState.STREAMING and self.agent is not None:
            self.agent.request_cancel()

    def action_copy_or_quit(self) -> None:
        """有选中文字时复制，否则沿用 Ctrl+C 安全退出。"""

        selected_text = self.screen.get_selected_text()
        if selected_text:
            self.copy_to_clipboard(selected_text)
            return

        if self.session_state is SessionState.STREAMING:
            self.action_cancel_turn()
            return

        self.action_safe_quit()
