"""Dragon Code 的 Textual 终端界面。"""

import os
import time
from collections.abc import Callable
from enum import Enum

from rich.console import Group
from rich.markdown import Markdown
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import OptionList, RichLog, Static, TextArea
from textual.worker import Worker

from dragon_code import __version__
from dragon_code.models import AppConfig, ProviderConfig
from dragon_code.prompt import SYSTEM_PROMPT, render_banner
from dragon_code.providers.base import BaseProvider, ProviderError
from dragon_code.providers.factory import create_provider
from dragon_code.session import ChatSession, Conversation


class SessionState(Enum):
    """当前终端会话所处的状态。"""

    SELECTING = "selecting"
    IDLE = "idle"
    STREAMING = "streaming"


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
        Binding("ctrl+c", "safe_quit", show=False, priority=True),
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
        self.session: ChatSession | None = None
        self.reply_buffer = ""
        self.turn_start = 0.0
        self.timer: Timer | None = None
        self.stream_worker: Worker | None = None
        self.spinner_index = 0

    def compose(self) -> ComposeResult:
        yield Static(render_banner(__version__, os.getcwd()), id="banner")
        yield Static("● 对话服务已就绪", id="ready")
        yield RichLog(id="conversation", wrap=True, highlight=False, markup=False)
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
        self.session = ChatSession(self.provider, Conversation(), SYSTEM_PROMPT)
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

        self._start_turn(text)

    def _start_turn(self, user_text: str) -> None:
        """更新界面状态并启动异步模型请求。"""

        conversation = self.query_one("#conversation", RichLog)
        conversation.write(Text(f"❯ {user_text}", style="bold cyan"))

        input_widget = self.query_one("#message-input", MessageInput)
        input_widget.load_text("")
        input_widget.disabled = True

        self.reply_buffer = ""
        self.turn_start = time.monotonic()
        self.spinner_index = 0
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
        """消费 ChatSession 事件并实时更新界面。"""

        if self.session is None:
            self._finish_with_error(ProviderError("unknown", "当前没有可用的 Provider。"))
            return

        async for event in self.session.stream_turn(user_text):
            if event.type == "text":
                self.reply_buffer += event.text
                self.query_one("#streaming", Static).update(self.reply_buffer)
            elif event.type == "completed":
                self._finish_with_reply(event.text)
            elif event.type == "error":
                error = event.error
                if isinstance(error, ProviderError):
                    self._finish_with_error(error)
                else:
                    self._finish_with_error(ProviderError("unknown", "模型请求失败，请稍后再试。"))

    def _update_timer(self) -> None:
        """刷新等待动画和已用秒数。"""

        if self.session_state is not SessionState.STREAMING:
            return

        frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        frame = frames[self.spinner_index % len(frames)]
        self.spinner_index += 1
        elapsed = int(time.monotonic() - self.turn_start)
        self.query_one("#timer", Static).update(f"{frame} Imagining… ({elapsed}s)")

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

    def _finish_with_reply(self, reply: str) -> None:
        """把完整回复定型为 Markdown 并写入历史区。"""

        elapsed = self._stop_turn()
        rendered = Group(
            Markdown(reply),
            Text(f"完成 · {elapsed:.1f}s", style="dim"),
        )
        self.query_one("#conversation", RichLog).write(rendered)

    def _finish_with_error(self, error: ProviderError) -> None:
        """显示脱敏错误并允许用户继续对话。"""

        self._stop_turn()
        message = Text(f"● {error.message}", style="bold red")
        self.query_one("#conversation", RichLog).write(message)

    def action_safe_quit(self) -> None:
        """清理计时器和 Worker 后退出。"""

        if self.timer is not None:
            self.timer.stop()
            self.timer = None
        if self.stream_worker is not None:
            self.stream_worker.cancel()
            self.stream_worker = None
        self.exit()
