"""Dragon Code Textual 界面测试。"""

import asyncio
from pathlib import Path

from conftest import FakeClient
from rich.markdown import Markdown
from rich.text import Text
from textual.color import Color
from textual.events import MouseMove
from textual.widgets import Input, OptionList, RichLog, Static

from dragon_code.clients.base import LLMError
from dragon_code.command_screens import (
    ConfirmCommandScreen,
    MemoryCommandScreen,
    MemoryScreenResult,
    PermissionModeScreen,
    ReviewTargetScreen,
    SessionCommandScreen,
    SessionScreenResult,
    SkillManagementScreen,
)
from dragon_code.command_widgets import CommandCompletion
from dragon_code.hooks import HookEngine
from dragon_code.hooks.models import (
    HookAction,
    HookActionType,
    HookDefinition,
    HookEvent,
    HookExecution,
    HookSnapshot,
)
from dragon_code.memory import MemoryManager, MemoryOperation
from dragon_code.models import (
    AppConfig,
    ChatMessage,
    CompactEvent,
    LLMEvent,
    ProviderConfig,
    TokenUsage,
    ToolCall,
    ToolResult,
)
from dragon_code.permissions import ApprovalChoice, PermissionMode, PermissionRequest
from dragon_code.prompt import DO_PLAN_PROMPT
from dragon_code.session import Conversation
from dragon_code.sessions import SessionManager
from dragon_code.subagents.models import SubAgentEvent, TaskStatus
from dragon_code.tools import create_default_registry
from dragon_code.tui import (
    CommandHelpScreen,
    DragonCodeApp,
    MessageInput,
    PermissionApprovalScreen,
    SessionResumeScreen,
    SessionState,
    format_tool_call,
    format_tool_result,
)


def provider_config(name: str = "Fake", model: str = "fake-model") -> ProviderConfig:
    return ProviderConfig(name, "openai", "fake-key", model)


VALID_SUMMARY = """<analysis>草稿</analysis><summary>
1. 主要请求和意图：继续任务
2. 关键技术概念：上下文
3. 文件和代码段：无
4. 错误与修复：无
5. 问题解决过程：无
6. 用户消息原文：原话
7. 待办任务：继续
8. 当前工作和停止位置：测试
9. 可能的下一步：实现
</summary>"""


def app_with_client(fake_client: FakeClient) -> DragonCodeApp:
    config = AppConfig([provider_config(fake_client.name, fake_client.model)])
    return DragonCodeApp(config, client_factory=lambda _config: fake_client)


class BlockingHookExecutor:
    async def execute(self, hook, _context):
        return HookExecution(hook.name, hook.action.type, "blocked", "输入不符合规则", True)


class RecordingHookExecutor:
    def __init__(self):
        self.events = []

    async def execute(self, hook, context):
        self.events.append(context.event)
        return HookExecution(hook.name, hook.action.type, "success", "recorded")


def hook_definition(name: str, event: HookEvent, action: HookAction) -> HookDefinition:
    return HookDefinition(name, event, None, action, timeout=1)


def complete_response(
    content: str,
    *,
    calls: list[ToolCall] | None = None,
    usage: tuple[int, int] = (10, 2),
) -> list[LLMEvent]:
    """生成一轮完整的 FakeClient 响应。"""

    calls = calls or []
    events = [LLMEvent("tool_call", tool_call=call) for call in calls]
    events.extend(
        [
            LLMEvent("usage", usage=TokenUsage(*usage)),
            LLMEvent(
                "completed",
                message=ChatMessage("assistant", content, tool_calls=calls),
            ),
        ]
    )
    return events


async def wait_until_idle(app: DragonCodeApp, pilot, attempts: int = 30):
    for _ in range(attempts):
        if app.session_state is SessionState.IDLE:
            return
        await pilot.pause(0.02)
    raise AssertionError("应用未在预期时间内恢复 IDLE")


async def wait_until_state(app: DragonCodeApp, pilot, state: SessionState, attempts: int = 30):
    for _ in range(attempts):
        if app.session_state is state:
            return
        await pilot.pause(0.02)
    raise AssertionError(f"应用未在预期时间内进入 {state.value}")


async def test_single_provider_layout():
    app = app_with_client(FakeClient())

    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.pause()

        assert app.session_state is SessionState.IDLE
        banner = app.query_one("#banner", Static)
        banner_text = str(banner.render())
        assert "▐██▙▄▟██▌" in banner_text
        assert "Dragon Code" in banner_text
        assert "Multi-provider coding agent" in banner_text
        assert banner.styles.color == Color.parse("white")
        assert str(app.query_one("#provider-name", Static).render()) == "Fake · default"
        assert str(app.query_one("#model-name", Static).render()) == "fake-model"
        assert app.query_one("#message-input", MessageInput).has_focus


async def test_command_completion_fills_then_second_enter_executes():
    app = app_with_client(FakeClient())

    async with app.run_test(size=(100, 32)) as pilot:
        input_widget = app.query_one("#message-input", MessageInput)
        input_widget.load_text("/he")
        await pilot.pause()

        completion = app.query_one("#command-completion", CommandCompletion)
        assert completion.display is True
        assert "/help" in str(completion.render())

        await pilot.press("enter")
        await pilot.pause()
        assert input_widget.text == "/help"
        assert isinstance(app.screen, CommandHelpScreen) is False

        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, CommandHelpScreen)

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, CommandHelpScreen)


async def test_status_is_local_and_contains_complete_snapshot():
    client = FakeClient()
    app = app_with_client(client)

    async with app.run_test(size=(100, 32)) as pilot:
        app.query_one("#message-input", MessageInput).load_text("/status")
        await pilot.press("enter")
        await pilot.pause()

        text = "\n".join(line.text for line in app.query_one(RichLog).lines)
        assert "Dragon Code 状态" in text
        assert "Provider：Fake" in text
        assert "工具：内置 6 / MCP 0" in text
        assert client.requests == []
        assert app.agent is not None
        assert app.agent.conversation.get_messages() == []


async def test_fast_local_command_does_not_block_next_command():
    client = FakeClient()
    app = app_with_client(client)

    async with app.run_test(size=(100, 32)) as pilot:
        input_widget = app.query_one("#message-input", MessageInput)
        input_widget.load_text("/status")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        assert app.command_worker is None
        input_widget.load_text("/help")
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, CommandHelpScreen)
        assert client.requests == []


async def test_permission_command_switches_runtime_mode_only():
    app = app_with_client(FakeClient())

    async with app.run_test(size=(100, 32)) as pilot:
        app.query_one("#message-input", MessageInput).load_text("/permission")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, PermissionModeScreen)

        await pilot.press("down", "enter")
        await pilot.pause()

        assert app.agent is not None
        assert app.agent.mode is PermissionMode.ACCEPT_EDITS
        assert app.session_state is SessionState.IDLE
        assert "acceptEdits" in str(app.query_one("#provider-name", Static).render())


async def test_clear_creates_new_session_and_preserves_permission(tmp_path: Path):
    manager = SessionManager(tmp_path)
    app = DragonCodeApp(
        AppConfig([provider_config()]),
        session_manager=manager,
        client_factory=lambda _config: FakeClient(),
    )

    async with app.run_test(size=(100, 32)) as pilot:
        assert app.active_session is not None
        assert app.agent is not None
        old_id = app.active_session.session_id
        app.agent.set_permission_mode(PermissionMode.ACCEPT_EDITS)
        app.query_one("#message-input", MessageInput).load_text("/clear")
        await pilot.press("enter")
        await wait_until_idle(app, pilot)

        assert app.active_session.session_id != old_id
        assert app.agent.mode is PermissionMode.ACCEPT_EDITS
        assert app.agent.conversation.get_messages() == []
        assert (manager.sessions_root / old_id).exists()


async def test_memory_status_counts_two_levels(tmp_path: Path):
    manager = MemoryManager(tmp_path, tmp_path / "home")
    manager._apply_operations(
        [
            MemoryOperation(
                "create",
                "project",
                "project_knowledge",
                "项目",
                "project",
                content="项目知识",
            ),
            MemoryOperation(
                "create",
                "user",
                "user_preference",
                "偏好",
                "preference",
                content="用户偏好",
            ),
        ]
    )
    app = DragonCodeApp(
        AppConfig([provider_config()]),
        session_manager=SessionManager(tmp_path),
        memory_manager=manager,
        client_factory=lambda _config: FakeClient(),
    )

    async with app.run_test(size=(100, 32)) as pilot:
        app.query_one("#message-input", MessageInput).load_text("/status")
        await pilot.press("enter")
        await pilot.pause()

        text = "\n".join(line.text for line in app.query_one(RichLog).lines)
        assert "记忆：用户 1 / 项目 1" in text


async def test_review_uses_read_only_tools_and_keeps_mode(tmp_path: Path):
    (tmp_path / "demo.py").write_text("print('dragon')\n", encoding="utf-8")
    client = FakeClient(responses=[complete_response("审查报告")])
    app = DragonCodeApp(
        AppConfig([provider_config()]),
        session_manager=SessionManager(tmp_path),
        client_factory=lambda _config: client,
    )

    async with app.run_test(size=(100, 32)) as pilot:
        assert app.agent is not None
        app.agent.set_permission_mode(PermissionMode.ACCEPT_EDITS)
        app.query_one("#message-input", MessageInput).load_text("/review")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ReviewTargetScreen)

        app.screen.dismiss("demo.py")
        await wait_until_idle(app, pilot)
        for _ in range(30):
            if client.requests:
                break
            await pilot.pause(0.02)

        assert [tool.name for tool in client.requests[0].tools] == [
            "Read",
            "Glob",
            "Grep",
            "LoadSkill",
            "Agent",
            "TaskList",
            "TaskGet",
            "TaskStop",
            "SendMessage",
        ]
        assert app.agent.mode is PermissionMode.ACCEPT_EDITS
        # review 是 fork Skill：任务进入独立历史，不污染主会话。
        assert app.agent.conversation.get_messages() == []
        assert app.task_manager is not None
        tasks = app.task_manager.list()
        assert len(tasks) == 1
        assert tasks[0].description == "执行 review Skill"


async def test_session_command_confirms_before_deleting(tmp_path: Path):
    manager = SessionManager(tmp_path)
    old = manager.open_new("old-model")
    old.conversation.commit_messages([ChatMessage("user", "旧会话标题")])
    old_id = old.session_id
    old.writer.close()
    app = DragonCodeApp(
        AppConfig([provider_config()]),
        session_manager=manager,
        client_factory=lambda _config: FakeClient(),
    )

    async with app.run_test(size=(110, 34)) as pilot:
        app.query_one("#message-input", MessageInput).load_text("/session")
        await pilot.press("enter")
        for _ in range(20):
            await pilot.pause(0.02)
            if isinstance(app.screen, SessionCommandScreen):
                break
        assert isinstance(app.screen, SessionCommandScreen)
        await pilot.pause()

        app.screen.dismiss(SessionScreenResult("delete", old_id))
        await pilot.pause()
        assert isinstance(app.screen, ConfirmCommandScreen)
        assert (manager.sessions_root / old_id).exists()

        app.screen.dismiss(True)
        for _ in range(30):
            await pilot.pause(0.02)
            if not (manager.sessions_root / old_id).exists():
                break
        assert not (manager.sessions_root / old_id).exists()


async def test_memory_command_confirms_and_rebuilds_index(tmp_path: Path):
    memory = MemoryManager(tmp_path, tmp_path / "home")
    memory._apply_operations(
        [
            MemoryOperation(
                "create",
                "project",
                "project_knowledge",
                "待删除记忆",
                "delete-me",
                content="这是一条测试记忆。",
            )
        ]
    )
    memory.load_indexes()
    item = memory.list_memories()[0]
    app = DragonCodeApp(
        AppConfig([provider_config()]),
        session_manager=SessionManager(tmp_path),
        memory_manager=memory,
        client_factory=lambda _config: FakeClient(),
    )

    async with app.run_test(size=(110, 34)) as pilot:
        app.query_one("#message-input", MessageInput).load_text("/memory")
        await pilot.press("enter")
        for _ in range(20):
            await pilot.pause(0.02)
            if isinstance(app.screen, MemoryCommandScreen):
                break
        assert isinstance(app.screen, MemoryCommandScreen)
        await pilot.pause()

        app.screen.dismiss(MemoryScreenResult("delete", item))
        await pilot.pause()
        assert isinstance(app.screen, ConfirmCommandScreen)
        app.screen.dismiss(True)
        for _ in range(30):
            await pilot.pause(0.02)
            if (
                not (memory.project_memory_dir / item.filename).exists()
                and "待删除记忆" not in memory.current_index()
            ):
                break

        assert not (memory.project_memory_dir / item.filename).exists()
        assert "待删除记忆" not in memory.current_index()


async def test_multiple_provider_selection():
    configs = [provider_config("One", "model-one"), provider_config("Two", "model-two")]

    def factory(config):
        return FakeClient(chunks=[config.name])

    app = DragonCodeApp(AppConfig(configs), client_factory=factory)

    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.pause()
        assert app.screen.query_one(OptionList)

        await pilot.press("down", "enter")
        await pilot.pause()

        assert app.session_state is SessionState.IDLE
        assert str(app.query_one("#provider-name", Static).render()) == "Two · default"
        assert app.client is not None
        assert app.client.chunks == ["Two"]


async def test_provider_activation_creates_distinct_main_and_summary_clients():
    created_configs = []
    created_clients = []

    def factory(config):
        created_configs.append(config)
        client = FakeClient()
        client.config = config
        created_clients.append(client)
        return client

    config = provider_config(model="deepseek-v4-pro")
    config.summary_model = "deepseek-v4-flash"
    app = DragonCodeApp(AppConfig([config]), client_factory=factory)

    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.pause()

        assert [item.model for item in created_configs] == [
            "deepseek-v4-pro",
            "deepseek-v4-flash",
        ]
        assert app.client is created_clients[0]
        assert app.summary_client is created_clients[1]
        assert app.client is not app.summary_client


async def test_manual_compact_uses_summary_client_without_main_request():
    main_client = FakeClient()
    summary_client = FakeClient(events=complete_response(VALID_SUMMARY))

    def factory(config):
        client = summary_client if config.model == "deepseek-v4-flash" else main_client
        client.config = config
        return client

    config = provider_config(model="deepseek-v4-pro")
    config.summary_model = "deepseek-v4-flash"
    app = DragonCodeApp(AppConfig([config]), client_factory=factory)

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.agent.conversation.commit_messages([ChatMessage("user", "已有历史")])
        app.query_one("#message-input", MessageInput).load_text("/compact")
        await pilot.press("enter")
        await wait_until_idle(app, pilot)

        assert main_client.requests == []
        assert len(summary_client.requests) == 1
        assert summary_client.requests[0].tools == []
        history = app.agent.conversation.get_messages()
        assert all(message.content != "/compact" for message in history)
        assert history[0].content.startswith("<summary>")

        conversation = app.query_one("#conversation", RichLog)
        conversation.text_select_all()
        selected = app.screen.get_selected_text() or ""
        assert "上下文压缩完成" in selected


async def test_manual_compact_failure_hides_raw_exception_text():
    main_client = FakeClient()

    class UnsafeSummaryClient(FakeClient):
        async def stream(self, request):
            raise RuntimeError("sk-secret-value must not leak")
            yield  # pragma: no cover

    summary_client = UnsafeSummaryClient()

    def factory(config):
        return summary_client if config.model == "deepseek-v4-flash" else main_client

    config = provider_config(model="deepseek-v4-pro")
    config.summary_model = "deepseek-v4-flash"
    app = DragonCodeApp(AppConfig([config]), client_factory=factory)

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.agent.conversation.commit_messages([ChatMessage("user", "历史")])
        app.query_one("#message-input", MessageInput).load_text("/compact")
        await pilot.press("enter")
        await wait_until_idle(app, pilot)

        conversation = app.query_one("#conversation", RichLog)
        conversation.text_select_all()
        selected = app.screen.get_selected_text() or ""
        assert "上下文压缩失败" in selected
        assert "sk-secret-value" not in selected


async def test_escape_cancels_manual_compact_and_restores_input():
    main_client = FakeClient()
    summary_client = FakeClient(chunks=[VALID_SUMMARY], delay=10)

    def factory(config):
        return summary_client if config.model == "deepseek-v4-flash" else main_client

    config = provider_config(model="deepseek-v4-pro")
    config.summary_model = "deepseek-v4-flash"
    app = DragonCodeApp(AppConfig([config]), client_factory=factory)

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.agent.conversation.commit_messages([ChatMessage("user", "历史")])
        input_widget = app.query_one("#message-input", MessageInput)
        input_widget.load_text("/compact")
        await pilot.press("enter")
        await wait_until_state(app, pilot, SessionState.STREAMING)
        assert input_widget.disabled is True

        await pilot.press("escape")
        await wait_until_idle(app, pilot)

        assert input_widget.disabled is False
        assert app.agent.context_manager.circuit_breaker.consecutive_failures == 0


async def test_help_and_compact_event_messages_are_visible():
    app = app_with_client(FakeClient())

    async with app.run_test(size=(100, 30)) as pilot:
        input_widget = app.query_one("#message-input", MessageInput)
        input_widget.load_text("/help")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, CommandHelpScreen)
        app.screen.dismiss(None)
        await pilot.pause()
        app._write_compact_event(CompactEvent("auto_start", before_tokens=20_000))
        app._write_compact_event(
            CompactEvent("auto_complete", before_tokens=20_000, after_tokens=8_000)
        )
        app._write_compact_event(CompactEvent("auto_failed", message="安全失败"))
        app._write_compact_event(CompactEvent("circuit_tripped", message="已熔断"))
        await pilot.pause()

        conversation = app.query_one("#conversation", RichLog)
        conversation.text_select_all()
        selected = app.screen.get_selected_text() or ""
        assert "❯ /help" in selected
        assert "20000 → 8000 Token" in selected
        assert "安全失败" in selected
        assert "已熔断" in selected


async def test_alt_enter_inserts_newline_and_enter_submits():
    client = FakeClient(chunks=["收到"])
    app = app_with_client(client)

    async with app.run_test(size=(90, 30)) as pilot:
        input_widget = app.query_one("#message-input", MessageInput)
        input_widget.load_text("第一行")
        input_widget.move_cursor((0, len("第一行")))

        await pilot.press("alt+enter")
        input_widget.insert("第二行")
        await pilot.press("enter")
        await wait_until_idle(app, pilot)

        assert client.received_messages[-1].content == "第一行\n第二行"
        assert input_widget.text == ""


async def test_streaming_completion_and_markdown():
    client = FakeClient(chunks=["**你", "好**"], delay=0.1)
    app = app_with_client(client)

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


async def test_progress_and_token_usage_are_visible():
    client = FakeClient(
        responses=[
            complete_response("第一答", usage=(10, 3)),
            complete_response("第二答", usage=(5, 2)),
        ]
    )
    app = app_with_client(client)

    async with app.run_test(size=(100, 30)) as pilot:
        input_widget = app.query_one("#message-input", MessageInput)
        input_widget.load_text("第一问")
        await pilot.press("enter")
        await wait_until_idle(app, pilot)

        assert app.current_iteration == 1
        assert app.max_iterations == 50
        assert app.session_usage == TokenUsage(10, 3)

        input_widget.load_text("第二问")
        await pilot.press("enter")
        await wait_until_idle(app, pilot)

        token_text = str(app.query_one("#token-usage", Static).render())
        assert app.session_usage == TokenUsage(15, 5)
        assert "Token 20" in token_text
        assert "输入 15" in token_text
        assert "输出 5" in token_text


async def test_tool_events_render_in_scrollback_in_order():
    call = ToolCall("read-1", "Read", {"path": "pyproject.toml"})
    client = FakeClient(
        responses=[
            complete_response("先读取", calls=[call]),
            complete_response("读取完成"),
        ]
    )
    app = app_with_client(client)

    async with app.run_test(size=(100, 30)) as pilot:
        app.query_one("#message-input", MessageInput).load_text("读取配置")
        await pilot.press("enter")
        await wait_until_idle(app, pilot)

        conversation = app.query_one("#conversation", RichLog)
        conversation.text_select_all()
        selected = app.screen.get_selected_text() or ""
        assert selected.index("Read  pyproject.toml") < selected.index("读取完成")
        assert "project" in selected


async def test_tool_result_states_have_distinct_labels():
    app = app_with_client(FakeClient())

    async with app.run_test(size=(100, 30)) as pilot:
        app._write_tool_result(ToolResult("1", "Read", True, content="成功"))
        app._write_tool_result(
            ToolResult(
                "2",
                "Read",
                False,
                error_code="not_found",
                error_message="文件不存在",
            )
        )
        app._write_tool_result(
            ToolResult(
                "3",
                "Bash",
                False,
                error_code="cancelled",
                error_message="尚未开始",
            )
        )
        app._write_tool_result(
            ToolResult(
                "4",
                "Bash",
                False,
                error_code="cancel_outcome_unknown",
                error_message="无法确认",
            )
        )
        await pilot.pause()

        conversation = app.query_one("#conversation", RichLog)
        conversation.text_select_all()
        selected = app.screen.get_selected_text() or ""
        assert "✓ Read  读取 1 行" in selected
        assert "✗ Read" in selected
        assert "└ 文件不存在" in selected
        assert "● Bash  已取消 · 尚未开始" in selected
        assert "✗ Bash" in selected
        assert "└ 无法确认" in selected


def test_tool_result_summaries_hide_protocol_details():
    bash_result = ToolResult(
        "bash-1",
        "Bash",
        True,
        content="stdout:\ndone\nstderr:\n\nexit_code: 0",
        metadata={"stdout": "done\n", "stderr": "", "exit_code": 0},
    )
    agent_result = ToolResult(
        "agent-1",
        "Agent",
        True,
        content='{"background": false, "result": "很长的子任务原文"}',
    )

    assert format_tool_result(bash_result) == "stdout: done"
    assert format_tool_result(agent_result) == "子任务已完成"


async def test_tool_activity_is_transient_and_success_is_single_line():
    app = app_with_client(FakeClient())
    call = ToolCall("read-active", "Read", {"path": "src/dragon.py"})

    async with app.run_test(size=(100, 30)) as pilot:
        app._start_tool_display("main:read-active", call)
        await pilot.pause()

        assert list(app.active_tool_displays) == ["main:read-active"]
        activity = app.query_one("#tool-activity", Static)
        with app.console.capture() as capture:
            app.console.print(activity.render()._renderable)
        assert "● Read  src/dragon.py" in capture.get()

        app._finish_tool_display(
            "main:read-active",
            ToolResult("read-active", "Read", True, content="第一行\n第二行"),
        )
        await pilot.pause()

        assert app.active_tool_displays == {}
        conversation = app.query_one("#conversation", RichLog)
        conversation.text_select_all()
        selected = app.screen.get_selected_text() or ""
        assert selected.count("Read") == 1
        assert "✓ Read  src/dragon.py  读取 2 行" in selected


async def test_two_active_tools_keep_order_and_clear_independently():
    app = app_with_client(FakeClient())
    first = ToolCall("one", "Read", {"path": "one.py"})
    second = ToolCall("two", "Grep", {"pattern": "dragon", "path": "src"})

    async with app.run_test(size=(100, 30)) as pilot:
        app._start_tool_display("main:one", first)
        app._start_tool_display("main:two", second)
        await pilot.pause()

        assert list(app.active_tool_displays) == ["main:one", "main:two"]
        app._finish_tool_display("main:one", ToolResult("one", "Read", True, "内容"))
        assert list(app.active_tool_displays) == ["main:two"]
        app._finish_tool_display("main:two", ToolResult("two", "Grep", True, "a.py:1"))
        assert app.active_tool_displays == {}


async def test_subagent_tools_show_only_when_attached():
    app = app_with_client(FakeClient())
    foreground_call = ToolCall("front", "Read", {"path": "front.py"})
    background_call = ToolCall("back", "Read", {"path": "hidden.py"})

    async with app.run_test(size=(100, 30)) as pilot:
        app._write_subagent_event(
            SubAgentEvent(
                "tool_start",
                "task_front",
                "reader",
                "explore",
                True,
                tool_call=foreground_call,
            )
        )
        assert "sub:task_front:front" in app.active_tool_displays
        app._write_subagent_event(
            SubAgentEvent(
                "tool_end",
                "task_front",
                "reader",
                "explore",
                True,
                tool_result=ToolResult("front", "Read", True, "一行"),
            )
        )
        app._write_subagent_event(
            SubAgentEvent(
                "tool_start",
                "task_back",
                "background-reader",
                "explore",
                False,
                tool_call=background_call,
            )
        )
        await pilot.pause()

        conversation = app.query_one("#conversation", RichLog)
        conversation.text_select_all()
        selected = app.screen.get_selected_text() or ""
        assert "reader · Read  front.py" in selected
        assert "hidden.py" not in selected
        assert all("task_back" not in key for key in app.active_tool_displays)


async def test_subagent_status_hides_normal_id_and_failed_shows_id():
    app = app_with_client(FakeClient())
    long_summary = "摘要" * 100

    async with app.run_test(size=(100, 30)) as pilot:
        app._write_subagent_event(
            SubAgentEvent(
                "running",
                "task_normal",
                "permission-study",
                "explore",
                False,
                status=TaskStatus.RUNNING,
            )
        )
        app._write_subagent_event(
            SubAgentEvent(
                "completed",
                "task_normal",
                "permission-study",
                "explore",
                False,
                text=long_summary,
                status=TaskStatus.COMPLETED,
            )
        )
        app._write_subagent_event(
            SubAgentEvent(
                "failed",
                "task_failed",
                "broken-study",
                "explore",
                False,
                text="模型请求失败",
                status=TaskStatus.FAILED,
            )
        )
        await pilot.pause()

        conversation = app.query_one("#conversation", RichLog)
        conversation.text_select_all()
        selected = app.screen.get_selected_text() or ""
        assert "task_normal" not in selected
        assert "✓ Agent  permission-study  已完成" in selected
        assert "摘要" * 40 not in selected
        assert "✗ Agent  broken-study  执行失败" in selected
        assert "task_failed" in selected


async def test_plan_mode_and_do_command():
    client = FakeClient(
        responses=[
            complete_response("计划：先读取，再修改"),
            complete_response("已经按计划完成"),
        ]
    )
    app = app_with_client(client)

    async with app.run_test(size=(100, 30)) as pilot:
        input_widget = app.query_one("#message-input", MessageInput)
        input_widget.load_text("/plan")
        await pilot.press("enter")
        await pilot.pause()

        assert app.agent is not None
        assert app.agent.mode == "plan"
        assert len(client.requests) == 0
        assert "Plan Mode" in str(app.query_one("#ready", Static).render())

        input_widget.load_text("分析修改方案")
        await pilot.press("enter")
        await wait_until_idle(app, pilot)

        assert app.agent.can_execute_plan() is True
        assert [tool.name for tool in client.requests[0].tools] == [
            "Read",
            "Glob",
            "Grep",
            "LoadSkill",
            "Agent",
            "TaskList",
            "TaskGet",
            "TaskStop",
            "SendMessage",
        ]

        input_widget.load_text("/do")
        await pilot.press("enter")
        await wait_until_idle(app, pilot)

        assert app.agent.mode == "default"
        assert client.requests[1].messages[-1].content == DO_PLAN_PROMPT
        assert len(client.requests[1].tools) == 12
        assert client.requests[1].tools[-1].name == "SendMessage"
        assert "Default" in str(app.query_one("#ready", Static).render())


async def test_permission_screen_defaults_to_allow_once_and_accepts_enter():
    app = app_with_client(FakeClient())
    selected = []
    call = ToolCall("write", "Write", {"path": "demo.txt", "content": "x"})
    request = PermissionRequest(call, "default 模式需要确认", "Write(demo.txt)", "Write(demo.txt)")

    async with app.run_test(size=(90, 30)) as pilot:
        app.session_state = SessionState.APPROVING
        app.push_screen(PermissionApprovalScreen(request), callback=selected.append)
        await pilot.pause()

        options = app.screen.query_one("#permission-options", OptionList)
        assert options.highlighted == 0
        assert "Write(demo.txt)" in str(
            app.screen.query_one("#permission-summary", Static).render()
        )

        await pilot.press("down", "enter")
        await pilot.pause()
        assert selected == [ApprovalChoice.ALLOW_ALWAYS]


async def test_mcp_permission_screen_has_session_choice():
    app = app_with_client(FakeClient())
    selected = []
    call = ToolCall("mcp-1", "mcp__local__echo", {"text": "dragon"})
    request = PermissionRequest(call, "MCP 首次使用", "echo(text=dragon)", call.name)

    async with app.run_test(size=(90, 30)) as pilot:
        app.session_state = SessionState.APPROVING
        app.push_screen(PermissionApprovalScreen(request), callback=selected.append)
        await pilot.pause()

        options = app.screen.query_one("#permission-options", OptionList)
        assert options.option_count == 4
        await pilot.press("2")
        await pilot.pause()

    assert selected == [ApprovalChoice.ALLOW_SESSION]


async def test_app_uses_injected_registry(tmp_path):
    fake_client = FakeClient()
    config = AppConfig([provider_config(fake_client.name, fake_client.model)])
    registry = create_default_registry(tmp_path)
    app = DragonCodeApp(
        config,
        registry,
        client_factory=lambda _config: fake_client,
    )

    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.pause()
        assert app.agent is not None
        assert app.agent.registry.get("Read") is registry.get("Read")
        assert app.agent.registry.get("LoadSkill") is not None


async def test_skill_management_screen_lists_builtins_and_reloads():
    app = app_with_client(FakeClient())

    async with app.run_test(size=(100, 34)) as pilot:
        app.query_one("#message-input", MessageInput).load_text("/skill")
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, SkillManagementScreen)
        assert app.screen.query_one("#skill-command-options", OptionList).option_count >= 3
        await pilot.press("r")
        await pilot.pause()

        assert app.session_state is SessionState.IDLE
        assert app.command_registry.find("review") is not None
        assert app.command_registry.find("commit") is not None
        assert app.command_registry.find("test") is not None


async def test_shift_tab_cycles_permission_modes_and_updates_status():
    app = app_with_client(FakeClient())

    async with app.run_test(size=(90, 30)) as pilot:
        assert app.agent is not None
        assert app.agent.mode is PermissionMode.DEFAULT

        await pilot.press("shift+tab")
        assert app.agent.mode is PermissionMode.ACCEPT_EDITS
        assert str(app.query_one("#provider-name", Static).render()) == "Fake · acceptEdits"

        await pilot.press("shift+tab", "shift+tab", "shift+tab")
        assert app.agent.mode is PermissionMode.DEFAULT


async def test_write_permission_allow_once_runs_and_returns_to_idle(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tool_call = ToolCall("write", "Write", {"path": "approved.txt", "content": "ok"})
    client = FakeClient(
        responses=[
            complete_response("", calls=[tool_call]),
            complete_response("写入完成"),
        ]
    )
    app = app_with_client(client)

    async with app.run_test(size=(100, 30)) as pilot:
        app.query_one("#message-input", MessageInput).load_text("写文件")
        await pilot.press("enter")
        await wait_until_state(app, pilot, SessionState.APPROVING)

        assert app.query_one("#message-input", MessageInput).disabled is True
        assert "Imagining" in str(app.query_one("#timer", Static).render())
        await pilot.press("1")
        await wait_until_idle(app, pilot)

        assert (tmp_path / "approved.txt").read_text(encoding="utf-8") == "ok"
        conversation = app.query_one("#conversation", RichLog)
        conversation.text_select_all()
        assert "写入完成" in (app.screen.get_selected_text() or "")


async def test_escape_cancels_permission_without_exiting(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tool_call = ToolCall("write", "Write", {"path": "cancelled.txt", "content": "no"})
    client = FakeClient(
        responses=[
            complete_response("", calls=[tool_call]),
            complete_response("取消后恢复"),
        ]
    )
    app = app_with_client(client)

    async with app.run_test(size=(100, 30)) as pilot:
        app.query_one("#message-input", MessageInput).load_text("写文件")
        await pilot.press("enter")
        await wait_until_state(app, pilot, SessionState.APPROVING)

        await pilot.press("escape")
        await wait_until_idle(app, pilot)

        assert app.is_running is True
        assert not (tmp_path / "cancelled.txt").exists()
        assert app.query_one("#message-input", MessageInput).disabled is False
        assert app.query_one("#message-input", MessageInput).has_focus is True

        # 即使真实终端没有把焦点正确还给 TextArea，应用级 Enter 也能兜底提交。
        app.set_focus(None)
        app.query_one("#message-input", MessageInput).load_text("继续")
        app.action_submit_current_input()
        await wait_until_idle(app, pilot)
        assert client.requests[-1].messages[-1].content == "继续"


async def test_plan_rejects_inline_task_and_do_without_plan():
    client = FakeClient(responses=[complete_response("内联计划")])
    app = app_with_client(client)

    async with app.run_test(size=(100, 30)) as pilot:
        input_widget = app.query_one("#message-input", MessageInput)
        input_widget.load_text("/do")
        await pilot.press("enter")
        await pilot.pause()
        assert len(client.requests) == 0

        input_widget.load_text("/plan 分析项目结构")
        await pilot.press("enter")
        await pilot.pause()

        assert client.requests == []

        input_widget.load_text("/plan")
        await pilot.press("enter")
        await pilot.pause()
        input_widget.load_text("分析项目结构")
        await pilot.press("enter")
        await wait_until_idle(app, pilot)

        assert client.requests[0].messages[-1].content == "分析项目结构"
        assert app.agent is not None
        assert app.agent.can_execute_plan() is True


class CancelThenSucceedClient(FakeClient):
    """第一轮阻塞供取消，第二轮正常完成。"""

    def __init__(self):
        super().__init__()
        self.calls = 0
        self.started = asyncio.Event()
        self.closed = False

    async def stream(self, request):
        self.calls += 1
        if self.calls == 1:
            try:
                self.started.set()
                yield LLMEvent("text_delta", text="部分回复")
                await asyncio.sleep(10)
            finally:
                self.closed = True
            return

        yield LLMEvent("text_delta", text="取消后恢复成功")
        yield LLMEvent("usage", usage=TokenUsage(2, 1))
        yield LLMEvent(
            "completed",
            message=ChatMessage("assistant", "取消后恢复成功"),
        )


async def test_escape_cancels_turn_and_next_message_succeeds():
    client = CancelThenSucceedClient()
    app = app_with_client(client)

    async with app.run_test(size=(100, 30)) as pilot:
        input_widget = app.query_one("#message-input", MessageInput)
        input_widget.load_text("慢任务")
        await pilot.press("enter")
        await client.started.wait()

        await pilot.press("escape")
        await wait_until_idle(app, pilot)

        assert app.is_running is True
        assert client.closed is True
        assert app.agent is not None
        assert app.agent.conversation.get_messages() == []

        input_widget.load_text("继续")
        await pilot.press("enter")
        await wait_until_idle(app, pilot)

        assert client.calls == 2
        assert app.reply_buffer == "取消后恢复成功"


async def test_ctrl_c_cancels_streaming_but_idle_escape_does_nothing():
    client = CancelThenSucceedClient()
    app = app_with_client(client)

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.press("escape")
        await pilot.pause()
        assert app.is_running is True

        app.query_one("#message-input", MessageInput).load_text("慢任务")
        await pilot.press("enter")
        await client.started.wait()
        await pilot.press("ctrl+c")
        await wait_until_idle(app, pilot)

        assert app.is_running is True
        assert client.closed is True


async def test_error_recovers_and_next_turn_succeeds():
    class FailThenSucceedClient(FakeClient):
        def __init__(self):
            super().__init__()
            self.calls = 0

        async def stream(self, request):
            self.calls += 1
            if self.calls == 1:
                raise LLMError("authentication", "鉴权失败")
            yield LLMEvent("text_delta", text="恢复成功")
            yield LLMEvent("completed", message=ChatMessage("assistant", "恢复成功"))

    client = FailThenSucceedClient()
    app = app_with_client(client)

    async with app.run_test(size=(90, 30)) as pilot:
        input_widget = app.query_one("#message-input", MessageInput)
        input_widget.load_text("第一次")
        await pilot.press("enter")
        await wait_until_idle(app, pilot)

        assert input_widget.disabled is False

        input_widget.load_text("第二次")
        await pilot.press("enter")
        await wait_until_idle(app, pilot)

        assert client.calls == 2
        assert app.reply_buffer == "恢复成功"


async def test_streaming_rejects_second_submit():
    class CountingClient(FakeClient):
        def __init__(self):
            super().__init__(chunks=["完成"], delay=0.1)
            self.calls = 0

        async def stream(self, request):
            self.calls += 1
            async for event in super().stream(request):
                yield event

    client = CountingClient()
    app = app_with_client(client)

    async with app.run_test(size=(90, 30)) as pilot:
        app.query_one("#message-input", MessageInput).load_text("第一条")
        await pilot.press("enter")
        await pilot.pause(0.02)

        app.on_message_input_submitted(MessageInput.Submitted("第二条"))
        await wait_until_idle(app, pilot)

        assert client.calls == 1


async def test_exit_command():
    app = app_with_client(FakeClient())

    async with app.run_test(size=(80, 24)) as pilot:
        app.query_one("#message-input", MessageInput).load_text("/exit")
        await pilot.press("enter")
        await pilot.pause()

        assert app.is_running is False


async def test_ctrl_c_copies_selection_and_keeps_running():
    client = FakeClient(chunks=["仍可继续"])
    app = app_with_client(client)

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

        assert client.received_messages[-1].content == "复制后继续对话"


async def test_chat_history_selection_includes_all_message_types():
    app = app_with_client(FakeClient())

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
    app = app_with_client(FakeClient())

    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("ctrl+c")
        await pilot.pause()

        assert app.is_running is False


async def test_narrow_terminal_keeps_main_widgets():
    app = app_with_client(FakeClient())

    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.resize_terminal(42, 18)
        await pilot.pause()

        assert app.query_one("#conversation", RichLog).region.width > 0
        assert app.query_one("#message-input", MessageInput).region.width > 0
        assert Path(app.CSS_PATH).name == "dragon_code.tcss"


async def test_session_start_prompt_is_ready_for_first_request():
    action = HookAction(HookActionType.PROMPT, prompt="startup reminder")
    engine = HookEngine(
        HookSnapshot((hook_definition("startup", HookEvent.SESSION_START, action),))
    )
    client = FakeClient(responses=[complete_response("完成")])
    config = AppConfig([provider_config(client.name, client.model)])
    app = DragonCodeApp(
        config,
        client_factory=lambda _config: client,
        hook_engine=engine,
    )

    async with app.run_test(size=(90, 30)) as pilot:
        await wait_until_idle(app, pilot)
        app.query_one("#message-input", MessageInput).load_text("第一条")
        await pilot.press("enter")
        await wait_until_idle(app, pilot)

        assert "startup reminder" in client.requests[0].reminder


async def test_user_prompt_hook_rejection_restores_input():
    action = HookAction(HookActionType.SHELL, command="unused")
    engine = HookEngine(
        HookSnapshot((hook_definition("block-input", HookEvent.USER_PROMPT_SUBMIT, action),))
    )
    engine.executor = BlockingHookExecutor()
    client = FakeClient()
    app = DragonCodeApp(
        AppConfig([provider_config()]),
        client_factory=lambda _config: client,
        hook_engine=engine,
    )

    async with app.run_test(size=(90, 30)) as pilot:
        await wait_until_idle(app, pilot)
        input_widget = app.query_one("#message-input", MessageInput)
        input_widget.load_text("被阻止的输入")
        await pilot.press("enter")
        await wait_until_idle(app, pilot)

        assert input_widget.text == "被阻止的输入"
        assert client.requests == []
        assert app.agent is not None
        assert app.agent.conversation.get_messages() == []
        text = "\n".join(line.text for line in app.query_one(RichLog).lines)
        assert "输入被 Hook 拒绝" in text


async def test_hooks_command_hides_action_body():
    action = HookAction(HookActionType.SHELL, command="echo VERY_SECRET_VALUE")
    engine = HookEngine(HookSnapshot((hook_definition("safe-list", HookEvent.STOP, action),)))
    app = DragonCodeApp(
        AppConfig([provider_config()]),
        client_factory=lambda _config: FakeClient(),
        hook_engine=engine,
    )

    async with app.run_test(size=(90, 30)) as pilot:
        await wait_until_idle(app, pilot)
        app.query_one("#message-input", MessageInput).load_text("/hooks")
        await pilot.press("enter")
        await pilot.pause()

        text = "\n".join(line.text for line in app.query_one(RichLog).lines)
        assert "safe-list" in text
        assert "VERY_SECRET_VALUE" not in text


async def test_session_hooks_cover_start_clear_end_and_resume(tmp_path):
    manager = SessionManager(tmp_path)
    saved = manager.open_new("fake-model")
    saved.conversation.commit_messages(
        [ChatMessage("user", "saved"), ChatMessage("assistant", "ok")]
    )
    saved_id = saved.session_id
    saved.writer.close()

    action = HookAction(HookActionType.SUBAGENT, task="record")
    hooks = tuple(
        hook_definition(f"watch-{event.value}", event, action)
        for event in (HookEvent.SESSION_START, HookEvent.SESSION_END, HookEvent.SESSION_RESUME)
    )
    engine = HookEngine(HookSnapshot(hooks))
    recorder = RecordingHookExecutor()
    engine.executor = recorder
    app = DragonCodeApp(
        AppConfig([provider_config()]),
        session_manager=manager,
        client_factory=lambda _config: FakeClient(),
        hook_engine=engine,
    )

    async with app.run_test(size=(90, 30)) as pilot:
        await wait_until_idle(app, pilot)
        assert recorder.events == [HookEvent.SESSION_START]

        app.clear_session()
        await wait_until_idle(app, pilot)
        assert recorder.events[-2:] == [HookEvent.SESSION_END, HookEvent.SESSION_START]

        app.session_state = SessionState.RESUMING
        app.query_one("#message-input", MessageInput).disabled = True
        await app._restore_session(saved_id)
        await pilot.pause()
        assert recorder.events[-2:] == [HookEvent.SESSION_END, HookEvent.SESSION_RESUME]


def test_tool_line_and_result_summary_are_short():
    call = ToolCall("1", "Read", {"path": "src/app.py"})
    success = ToolResult("1", "Read", True, content="x" * 500, truncated=True)
    failure = ToolResult("2", "Read", False, error_message="文件不存在")
    assert format_tool_call(call) == "● Read  src/app.py"
    assert len(format_tool_result(success)) < 120
    assert "已截断" in format_tool_result(success)
    offloaded = ToolResult(
        "3",
        "Read",
        True,
        content="预览",
        metadata={"context_offloaded": True},
        truncated=True,
    )
    assert "完整结果已保存" in format_tool_result(offloaded)
    assert format_tool_result(failure) == "文件不存在"


async def test_resume_screen_filters_and_restores_original_session(tmp_path):
    source_manager = SessionManager(tmp_path)
    source = source_manager.open_new("saved-model")
    source.conversation.commit_messages(
        [
            ChatMessage("user", "unique dragon title"),
            ChatMessage("assistant", "saved answer"),
        ]
    )
    source_id = source.session_id
    source_manager.close()

    manager = SessionManager(tmp_path)
    client = FakeClient()
    config = AppConfig([provider_config(client.name, client.model)])
    app = DragonCodeApp(
        config,
        client_factory=lambda _config: client,
        session_manager=manager,
    )

    async with app.run_test(size=(100, 32)) as pilot:
        input_widget = app.query_one("#message-input", MessageInput)
        input_widget.load_text("/resume")
        await pilot.press("enter")
        for _ in range(30):
            if isinstance(app.screen, SessionResumeScreen):
                break
            await pilot.pause(0.02)
        assert isinstance(app.screen, SessionResumeScreen)

        search = app.screen.query_one("#resume-search", Input)
        search.value = "unique dragon"
        await pilot.pause()
        assert app.screen.query_one("#resume-options", OptionList).option_count == 1

        await pilot.press("enter")
        await wait_until_idle(app, pilot, attempts=80)

        assert app.active_session is not None
        assert app.active_session.session_id == source_id
        assert app.agent is not None
        assert [message.content for message in app.agent.conversation.get_messages()] == [
            "unique dragon title",
            "saved answer",
        ]


async def test_resume_failure_keeps_old_conversation(tmp_path, monkeypatch):
    manager = SessionManager(tmp_path)
    client = FakeClient()
    app = DragonCodeApp(
        AppConfig([provider_config()]),
        client_factory=lambda _config: client,
        session_manager=manager,
    )

    async with app.run_test(size=(90, 30)) as pilot:
        assert app.agent is not None
        old_conversation = app.agent.conversation

        def fail_restore(_session_id, _model):
            raise OSError("broken file")

        monkeypatch.setattr(manager, "restore", fail_restore)
        app.session_state = SessionState.RESUMING
        app.query_one("#message-input", MessageInput).disabled = True

        await app._restore_session("20260811-120000-abcd")
        await pilot.pause()

        assert app.session_state is SessionState.IDLE
        assert app.agent.conversation is old_conversation
        assert "恢复失败" in "\n".join(line.text for line in app.query_one(RichLog).lines)


async def test_resume_during_stream_only_shows_wait_notice():
    client = FakeClient(chunks=["完成"], delay=0.1)
    app = app_with_client(client)

    async with app.run_test(size=(90, 30)) as pilot:
        app.query_one("#message-input", MessageInput).load_text("运行中")
        await pilot.press("enter")
        await wait_until_state(app, pilot, SessionState.STREAMING)

        app.on_message_input_submitted(MessageInput.Submitted("/resume"))
        await wait_until_idle(app, pilot)

        text = "\n".join(line.text for line in app.query_one(RichLog).lines)
        assert "当前任务结束或取消后再执行命令" in text


async def test_session_warning_is_visible_and_next_turn_can_continue(tmp_path):
    client = FakeClient(chunks=["正常回复"])
    app = app_with_client(client)

    async with app.run_test(size=(90, 30)) as pilot:
        assert app.agent is not None

        def fail(_message):
            raise OSError("disk full")

        app.agent.conversation = Conversation(on_append=fail)
        app.query_one("#message-input", MessageInput).load_text("第一轮")
        await pilot.press("enter")
        await wait_until_idle(app, pilot)

        text = "\n".join(line.text for line in app.query_one(RichLog).lines)
        assert "本轮未能保存" in text
        assert "正常回复" in text
        assert app.query_one("#message-input", MessageInput).disabled is False
