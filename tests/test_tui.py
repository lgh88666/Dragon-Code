"""Dragon Code Textual 界面测试。"""

from pathlib import Path

from conftest import FakeProvider
from rich.markdown import Markdown
from rich.text import Text
from textual.color import Color
from textual.events import MouseMove
from textual.widgets import OptionList, RichLog, Static

from dragon_code.models import (
    AppConfig,
    ChatMessage,
    ProviderConfig,
    ProviderEvent,
    ToolCall,
    ToolResult,
)
from dragon_code.providers.base import ProviderError
from dragon_code.tui import (
    DragonCodeApp,
    MessageInput,
    SessionState,
    format_tool_call,
    format_tool_result,
)


def provider_config(name: str = "Fake", model: str = "fake-model") -> ProviderConfig:
    return ProviderConfig(name, "openai", "fake-key", model)


def app_with_provider(fake_provider: FakeProvider) -> DragonCodeApp:
    config = AppConfig([provider_config(fake_provider.name, fake_provider.model)])
    return DragonCodeApp(config, provider_factory=lambda _config: fake_provider)


async def wait_until_idle(app: DragonCodeApp, pilot, attempts: int = 30):
    for _ in range(attempts):
        if app.session_state is SessionState.IDLE:
            return
        await pilot.pause(0.02)
    raise AssertionError("应用未在预期时间内恢复 IDLE")


async def test_single_provider_layout():
    app = app_with_provider(FakeProvider())

    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.pause()

        assert app.session_state is SessionState.IDLE
        banner = app.query_one("#banner", Static)
        banner_text = str(banner.render())
        assert "▐██▙▄▟██▌" in banner_text
        assert "Dragon Code" in banner_text
        assert "Multi-provider coding agent" in banner_text
        assert banner.styles.color == Color.parse("white")
        assert str(app.query_one("#provider-name", Static).render()) == "Fake"
        assert str(app.query_one("#model-name", Static).render()) == "fake-model"
        assert app.query_one("#message-input", MessageInput).has_focus


async def test_multiple_provider_selection():
    configs = [provider_config("One", "model-one"), provider_config("Two", "model-two")]

    def factory(config):
        return FakeProvider(chunks=[config.name])

    app = DragonCodeApp(AppConfig(configs), provider_factory=factory)

    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.pause()
        assert app.screen.query_one(OptionList)

        await pilot.press("down", "enter")
        await pilot.pause()

        assert app.session_state is SessionState.IDLE
        assert str(app.query_one("#provider-name", Static).render()) == "Fake"
        assert app.provider is not None
        assert app.provider.chunks == ["Two"]


async def test_alt_enter_inserts_newline_and_enter_submits():
    provider = FakeProvider(chunks=["收到"])
    app = app_with_provider(provider)

    async with app.run_test(size=(90, 30)) as pilot:
        input_widget = app.query_one("#message-input", MessageInput)
        input_widget.load_text("第一行")
        input_widget.move_cursor((0, len("第一行")))

        await pilot.press("alt+enter")
        input_widget.insert("第二行")
        await pilot.press("enter")
        await wait_until_idle(app, pilot)

        assert provider.received_messages[-1].content == "第一行\n第二行"
        assert input_widget.text == ""


async def test_streaming_completion_and_markdown():
    provider = FakeProvider(chunks=["**你", "好**"], delay=0.1)
    app = app_with_provider(provider)

    async with app.run_test(size=(90, 30)) as pilot:
        app.query_one("#message-input", MessageInput).load_text("问候")
        await pilot.press("enter")
        await pilot.pause(0.02)

        assert app.session_state is SessionState.STREAMING
        assert "Imagining" in str(app.query_one("#timer", Static).render())

        await wait_until_idle(app, pilot)
        assert app.reply_buffer == "**你好**"
        assert str(app.query_one("#streaming", Static).render()) == ""
        assert len(app.query_one("#conversation", RichLog).lines) > 0


async def test_error_recovers_and_next_turn_succeeds():
    class FailThenSucceedProvider(FakeProvider):
        def __init__(self):
            super().__init__()
            self.calls = 0

        async def stream(self, messages, system_prompt, tools):
            self.calls += 1
            if self.calls == 1:
                raise ProviderError("authentication", "鉴权失败")
            yield ProviderEvent("text_delta", text="恢复成功")
            yield ProviderEvent("completed", message=ChatMessage("assistant", "恢复成功"))

    provider = FailThenSucceedProvider()
    app = app_with_provider(provider)

    async with app.run_test(size=(90, 30)) as pilot:
        input_widget = app.query_one("#message-input", MessageInput)
        input_widget.load_text("第一次")
        await pilot.press("enter")
        await wait_until_idle(app, pilot)

        assert input_widget.disabled is False

        input_widget.load_text("第二次")
        await pilot.press("enter")
        await wait_until_idle(app, pilot)

        assert provider.calls == 2
        assert app.reply_buffer == "恢复成功"


async def test_streaming_rejects_second_submit():
    class CountingProvider(FakeProvider):
        def __init__(self):
            super().__init__(chunks=["完成"], delay=0.1)
            self.calls = 0

        async def stream(self, messages, system_prompt, tools):
            self.calls += 1
            async for event in super().stream(messages, system_prompt, tools):
                yield event

    provider = CountingProvider()
    app = app_with_provider(provider)

    async with app.run_test(size=(90, 30)) as pilot:
        app.query_one("#message-input", MessageInput).load_text("第一条")
        await pilot.press("enter")
        await pilot.pause(0.02)

        app.on_message_input_submitted(MessageInput.Submitted("第二条"))
        await wait_until_idle(app, pilot)

        assert provider.calls == 1


async def test_exit_command():
    app = app_with_provider(FakeProvider())

    async with app.run_test(size=(80, 24)) as pilot:
        app.query_one("#message-input", MessageInput).load_text("/exit")
        await pilot.press("enter")
        await pilot.pause()

        assert app.is_running is False


async def test_ctrl_c_copies_selection_and_keeps_running():
    provider = FakeProvider(chunks=["仍可继续"])
    app = app_with_provider(provider)

    async with app.run_test(size=(80, 24)) as pilot:
        conversation = app.query_one("#conversation", RichLog)
        conversation.write("需要复制的聊天内容")
        await pilot.pause()

        # Pilot 没有公开的 drag 方法，因此组合鼠标按下、移动和松开来模拟拖选。
        await pilot.mouse_down(conversation, offset=(0, 0))
        await pilot._post_mouse_events(
            [MouseMove],
            conversation,
            offset=(18, 0),
            button=1,
        )
        await pilot.mouse_up(conversation, offset=(18, 0))
        selected_text = app.screen.get_selected_text()
        assert selected_text is not None
        assert selected_text == "需要复制的聊天内容"

        line_count = len(conversation.lines)
        await pilot.press("ctrl+c")
        await pilot.pause()

        assert app.clipboard == selected_text
        assert app.is_running is True
        assert len(conversation.lines) == line_count

        input_widget = app.query_one("#message-input", MessageInput)
        input_widget.focus()
        input_widget.load_text("复制后继续对话")
        await pilot.press("enter")
        await wait_until_idle(app, pilot)

        assert provider.received_messages[-1].content == "复制后继续对话"


async def test_chat_history_selection_includes_all_message_types():
    app = app_with_provider(FakeProvider())

    async with app.run_test(size=(80, 24)) as pilot:
        conversation = app.query_one("#conversation", RichLog)
        conversation.write(Text("❯ 用户消息"))
        conversation.write(Markdown("助手回复\n\n```python\nprint('dragon')\n```"))
        conversation.write(Text("● Read(src/app.py)"))
        conversation.write(Text("错误：文件不存在"))
        await pilot.pause()

        conversation.text_select_all()
        selected_text = app.screen.get_selected_text()

        assert selected_text is not None
        assert "用户消息" in selected_text
        assert "助手回复" in selected_text
        assert "print('dragon')" in selected_text
        assert "Read(src/app.py)" in selected_text
        assert "文件不存在" in selected_text


async def test_ctrl_c_exit():
    app = app_with_provider(FakeProvider())

    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("ctrl+c")
        await pilot.pause()

        assert app.is_running is False


async def test_narrow_terminal_keeps_main_widgets():
    app = app_with_provider(FakeProvider())

    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.resize_terminal(42, 18)
        await pilot.pause()

        assert app.query_one("#conversation", RichLog).region.width > 0
        assert app.query_one("#message-input", MessageInput).region.width > 0
        assert Path(app.CSS_PATH).name == "dragon_code.tcss"


def test_tool_line_and_result_summary_are_short():
    call = ToolCall("1", "Read", {"path": "src/app.py"})
    success = ToolResult("1", "Read", True, content="x" * 500, truncated=True)
    failure = ToolResult("2", "Read", False, error_message="文件不存在")
    assert format_tool_call(call) == "● Read(src/app.py)"
    assert len(format_tool_result(success)) < 270
    assert "已截断" in format_tool_result(success)
    assert format_tool_result(failure) == "文件不存在"
