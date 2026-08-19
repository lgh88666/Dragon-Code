"""Dragon Code 的 Textual 终端界面。"""

import asyncio
import json
import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
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
from textual.widgets import Input, OptionList, RichLog, Static, TextArea
from textual.worker import Worker

from dragon_code import __version__
from dragon_code.agent import Agent
from dragon_code.clients.base import LLMClient, LLMError
from dragon_code.clients.factory import create_llm_client
from dragon_code.command import (
    Command,
    CommandStatus,
    CompletionState,
    create_command_registry,
    dispatch_command,
)
from dragon_code.command_screens import (
    CommandHelpScreen,
    ConfirmCommandScreen,
    MemoryCommandScreen,
    MemoryScreenResult,
    PermissionModeScreen,
    ReviewTargetScreen,
    SessionCommandScreen,
    SessionScreenResult,
    SkillManagementScreen,
    SkillScreenResult,
)
from dragon_code.command_widgets import CommandCompletion
from dragon_code.context.manager import ContextManager
from dragon_code.context.summary import estimate_message_tokens
from dragon_code.hooks import HookEngine
from dragon_code.hooks.models import HookEvent, HookExecution, HookSnapshot
from dragon_code.memory import MemoryInfo, MemoryManager
from dragon_code.models import (
    AppConfig,
    ProviderConfig,
    TokenUsage,
    ToolCall,
    ToolResult,
)
from dragon_code.permissions import ApprovalChoice, PathSandbox, PermissionMode, PermissionRequest
from dragon_code.permissions.approval import ApprovalController
from dragon_code.permissions.engine import PermissionEngine
from dragon_code.permissions.rules import RuleStore
from dragon_code.prompt import DO_PLAN_PROMPT, build_system_prompt, render_banner
from dragon_code.sessions import ActiveSession, SessionInfo, SessionManager
from dragon_code.skills import SkillExecutor, SkillLoader, SkillManager
from dragon_code.skills.tools import LoadSkillTool, registry_for_skill_tools
from dragon_code.subagents.catalog import AgentCatalog, AgentDefinitionLoader
from dragon_code.subagents.host import SubAgentHost
from dragon_code.subagents.manager import BackgroundTaskManager
from dragon_code.subagents.models import SubAgentEvent, TaskStatus
from dragon_code.subagents.tools import (
    AgentTool,
    SendMessageTool,
    create_subagent_tools,
)
from dragon_code.tools import ToolRegistry, create_default_registry

# 工具过程使用接近 Claude Code 的低饱和配色，避免抢过最终回答。
TOOL_ACCENT = "#c2a078"
TOOL_MUTED = "#8c8c86"
TOOL_ERROR = "#b86b6b"


@dataclass(frozen=True)
class PendingToolDisplay:
    """一个尚未完成、只显示在动态区域的工具调用。"""

    key: str
    call: ToolCall
    agent_label: str = ""


def _tool_key_argument(call: ToolCall) -> str:
    """提取最值得用户看到的关键参数。"""

    arguments = call.arguments or {}
    if call.name in {"Read", "Write", "Edit"}:
        key = arguments.get("path", "")
    elif call.name == "Bash":
        key = arguments.get("command", "")
    elif call.name == "Glob":
        key = arguments.get("pattern", "")
    elif call.name == "Grep":
        key = f"{arguments.get('pattern', '')} · {arguments.get('path', '.')}"
    elif call.name == "Agent":
        key = arguments.get("name") or arguments.get("description") or arguments.get("role", "")
    elif call.name in {"TaskGet", "TaskStop"}:
        key = arguments.get("task_id", "")
    elif call.name == "SendMessage":
        key = arguments.get("name", "")
    else:
        key = " · ".join(f"{name}={value}" for name, value in list(arguments.items())[:3])
    key = str(key).replace("\n", " ").strip()
    if len(key) > 92:
        key = key[:89] + "..."
    return key


def format_tool_subject(call: ToolCall, *, agent_label: str = "") -> str:
    """生成无状态符号的紧凑工具主题。"""

    source = f"{agent_label} · " if agent_label else ""
    key = _tool_key_argument(call)
    return f"{source}{call.name}  {key}".rstrip()


def format_tool_call(call: ToolCall) -> str:
    """保留给测试和简单调用方的执行中纯文本格式。"""

    return f"● {format_tool_subject(call)}"


def _system_tool_summary(result: ToolResult) -> str:
    """把任务工具 JSON 压缩成用户能快速扫读的摘要。"""

    if result.tool_name not in {"Agent", "TaskList", "TaskGet", "TaskStop", "SendMessage"}:
        return ""
    try:
        data = json.loads(result.content)
    except (TypeError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    if result.tool_name == "TaskList":
        tasks = data.get("tasks", [])
        return (
            f"{len(tasks)} 个任务 · {data.get('running', 0)} running · "
            f"{data.get('queued', 0)} queued"
        )
    if result.tool_name == "TaskGet":
        detail = data.get("result") or data.get("error") or data.get("status", "")
        return f"{data.get('task_id', '')} · {detail}".strip(" ·")
    if result.tool_name == "TaskStop":
        return f"{data.get('task_id', '')} · {data.get('status', '已停止')}".strip(" ·")
    if result.tool_name == "SendMessage":
        return f"新任务已创建 · {data.get('status', 'queued')}"
    if data.get("background"):
        return "后台任务已启动"
    return "子任务已完成"


def format_tool_result(result: ToolResult, *, limit: int = 100) -> str:
    """只为 TUI 生成短摘要，完整内容仍只回灌给模型。"""

    if result.success:
        system_summary = _system_tool_summary(result)
        if system_summary:
            text = system_summary
        elif result.tool_name == "Read":
            lines = result.content.splitlines()
            text = f"读取 {len(lines)} 行" if lines else "文件为空"
        elif result.tool_name == "Glob":
            count = len([line for line in result.content.splitlines() if line.strip()])
            text = f"找到 {count} 个文件"
        elif result.tool_name == "Grep":
            count = len([line for line in result.content.splitlines() if line.strip()])
            text = f"找到 {count} 处匹配"
        elif result.tool_name == "Bash":
            # Bash 的完整结果包含 stdout、stderr 和退出码，直接展示会撑成多行。
            stdout = str(result.metadata.get("stdout", "")).strip()
            text = f"stdout: {stdout}" if stdout else "命令执行成功"
        else:
            text = result.content or "执行成功"
    else:
        text = result.error_message or "执行失败"
    text = text.replace("\n", " ")
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    if result.truncated:
        suffix = "完整结果已保存" if result.metadata.get("context_offloaded") else "结果已截断"
        text += f"（{suffix}）"
    return text


class SessionState(Enum):
    """当前终端会话所处的状态。"""

    SELECTING = "selecting"
    IDLE = "idle"
    STREAMING = "streaming"
    APPROVING = "approving"
    RESUMING = "resuming"
    COMMAND = "command"


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
        Binding("up", "completion_up", show=False, priority=True),
        Binding("down", "completion_down", show=False, priority=True),
        Binding("tab", "completion_tab", show=False, priority=True),
    ]

    class Submitted(Message):
        """用户按 Enter 后发送给 DragonCodeApp 的消息。"""

        def __init__(self, value: str):
            super().__init__()
            self.value = value

    def action_submit(self) -> None:
        """提交完整输入，不在这里修改应用状态。"""

        if self.app.accept_completion():
            return
        self.post_message(self.Submitted(self.text))

    def action_insert_newline(self) -> None:
        """在当前光标位置插入换行。"""

        self.insert("\n")

    def action_completion_up(self) -> None:
        if not self.app.move_completion(-1):
            self.action_cursor_up()

    def action_completion_down(self) -> None:
        if not self.app.move_completion(1):
            self.action_cursor_down()

    def action_completion_tab(self) -> None:
        if self.app.completion_state.active:
            self.app.accept_completion()


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

    def submit_highlighted(self) -> None:
        options = self.query_one("#provider-options", OptionList)
        self.dismiss(options.highlighted or 0)


class SessionResumeScreen(ModalScreen[str | None]):
    """搜索并选择一个本地历史会话。"""

    BINDINGS = [Binding("escape", "cancel", show=False, priority=True)]

    def __init__(self, sessions: list[SessionInfo]):
        super().__init__()
        self.sessions = sessions
        self.filtered = list(sessions)

    def compose(self) -> ComposeResult:
        with Vertical(id="resume-dialog"):
            yield Static("恢复历史会话", id="resume-title")
            yield Input(placeholder="按标题或会话 ID 搜索…", id="resume-search")
            yield OptionList(*self._labels(self.filtered), id="resume-options")

    def on_mount(self) -> None:
        self.query_one("#resume-search", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        keyword = event.value.strip().lower()
        self.filtered = [
            session
            for session in self.sessions
            if not keyword
            or keyword in session.title.lower()
            or keyword in session.session_id.lower()
        ]
        options = self.query_one("#resume-options", OptionList)
        options.clear_options()
        options.add_options(self._labels(self.filtered) or ["没有匹配的会话"])

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_index < len(self.filtered):
            self.dismiss(self.filtered[event.option_index].session_id)

    def submit_highlighted(self) -> None:
        options = self.query_one("#resume-options", OptionList)
        index = options.highlighted or 0
        if index < len(self.filtered):
            self.dismiss(self.filtered[index].session_id)

    def action_cancel(self) -> None:
        self.dismiss(None)

    @staticmethod
    def _labels(sessions: list[SessionInfo]) -> list[str]:
        now = time.time()
        return [
            (
                f"{session.title}  ·  {_relative_time(now, session.updated_at.timestamp())}"
                f"  ·  {session.model}  ·  {_format_file_size(session.file_size)}"
            )
            for session in sessions
        ]


def _relative_time(now: float, timestamp: float) -> str:
    seconds = max(0, int(now - timestamp))
    if seconds < 60:
        return "刚刚"
    if seconds < 3600:
        return f"{seconds // 60} 分钟前"
    if seconds < 86400:
        return f"{seconds // 3600} 小时前"
    return f"{seconds // 86400} 天前"


def _format_file_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


class PermissionApprovalScreen(ModalScreen[ApprovalChoice | None]):
    """显示一次工具调用的权限确认。"""

    BINDINGS = [
        Binding("1", "allow_once", show=False, priority=True),
        Binding("2", "choose_second", show=False, priority=True),
        Binding("3", "choose_third", show=False, priority=True),
        Binding("4", "choose_fourth", show=False, priority=True),
        Binding("escape", "cancel", show=False, priority=True),
        Binding("ctrl+c", "cancel", show=False, priority=True),
    ]

    def __init__(self, request: PermissionRequest):
        super().__init__()
        self.request = request

    def compose(self) -> ComposeResult:
        labels = ["1. 允许本次"]
        if self._is_mcp_request():
            labels.append("2. 本会话允许该 MCP 工具")
            labels.append("3. 永久允许该 MCP 工具")
            labels.append("4. 拒绝本次")
        else:
            labels.append("2. 永久允许此精确调用")
            labels.append("3. 拒绝本次")

        with Vertical(id="permission-dialog"):
            yield Static("需要你的允许", id="permission-title")
            yield Static(self.request.summary, id="permission-summary")
            yield Static(self.request.reason, id="permission-reason")
            yield OptionList(*labels, id="permission-options")

    def on_mount(self) -> None:
        options = self.query_one("#permission-options", OptionList)
        options.highlighted = 0
        options.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(self._choices()[event.option_index])

    def action_allow_once(self) -> None:
        self.dismiss(ApprovalChoice.ALLOW_ONCE)

    def action_choose_second(self) -> None:
        self._dismiss_index(1)

    def action_choose_third(self) -> None:
        self._dismiss_index(2)

    def action_choose_fourth(self) -> None:
        self._dismiss_index(3)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def submit_highlighted(self) -> None:
        options = self.query_one("#permission-options", OptionList)
        self.dismiss(self._choices()[options.highlighted or 0])

    def _is_mcp_request(self) -> bool:
        return self.request.call.name.startswith("mcp__")

    def _choices(self) -> list[ApprovalChoice]:
        if self._is_mcp_request():
            return [
                ApprovalChoice.ALLOW_ONCE,
                ApprovalChoice.ALLOW_SESSION,
                ApprovalChoice.ALLOW_ALWAYS,
                ApprovalChoice.DENY_ONCE,
            ]
        return [
            ApprovalChoice.ALLOW_ONCE,
            ApprovalChoice.ALLOW_ALWAYS,
            ApprovalChoice.DENY_ONCE,
        ]

    def _dismiss_index(self, index: int) -> None:
        choices = self._choices()
        if index < len(choices):
            self.dismiss(choices[index])


class DragonCodeApp(App):
    """Dragon Code 主界面。"""

    CSS_PATH = "dragon_code.tcss"
    BINDINGS = [
        Binding("enter", "submit_current_input", show=False, priority=True),
        Binding("ctrl+c", "copy_or_quit", show=False, priority=True),
        Binding("escape", "cancel_turn", show=False, priority=True),
        Binding("ctrl+b", "background_current_subagent", show=False, priority=True),
        Binding("shift+tab", "cycle_permission_mode", show=False, priority=True),
    ]

    def __init__(
        self,
        config: AppConfig,
        registry: ToolRegistry | None = None,
        client_factory: Callable[[ProviderConfig], LLMClient] = create_llm_client,
        session_manager: SessionManager | None = None,
        memory_manager: MemoryManager | None = None,
        custom_instructions: str = "",
        skill_manager: SkillManager | None = None,
        hook_engine: HookEngine | None = None,
        agent_catalog: AgentCatalog | None = None,
    ):
        super().__init__()
        self.config = config
        self.session_manager = session_manager or SessionManager(Path.cwd())
        self.memory_manager = memory_manager
        self.custom_instructions = custom_instructions
        extra_read_roots = [memory_manager.user_memory_dir] if memory_manager is not None else []
        self.base_registry = registry or create_default_registry(
            self.session_manager.project_root,
            extra_read_roots,
        )
        self.registry = self.base_registry
        if skill_manager is None:
            base_commands = create_command_registry().visible()
            reserved = {
                name for command in base_commands for name in (command.name, *command.aliases)
            }
            skill_manager = SkillManager(
                SkillLoader(
                    self.session_manager.project_root,
                    user_home=self.session_manager.project_root / ".dragon-code" / "test-home",
                    reserved_commands=reserved,
                    base_tool_names=set(self.base_registry.names()) | {"LoadSkill"},
                )
            )
            skill_manager.reload()
        self.skill_manager = skill_manager
        self.hook_engine = hook_engine or HookEngine(HookSnapshot())
        self.agent_catalog = (
            agent_catalog
            or AgentDefinitionLoader(
                self.session_manager.project_root,
                user_home=self.session_manager.project_root / ".dragon-code" / "test-home",
            ).load()
        )
        self.task_manager: BackgroundTaskManager | None = None
        self.subagent_host: SubAgentHost | None = None
        self.subagent_tools = []
        self.subagent_buffers: dict[str, str] = {}
        self.active_tool_displays: dict[str, PendingToolDisplay] = {}
        self.skill_runtime = None
        self.skill_executor: SkillExecutor | None = None
        self.client_factory = client_factory
        skills = skill_manager.list_skills() if skill_manager is not None else []
        self.command_registry = create_command_registry(skills)
        self.completion_state = CompletionState()
        self.session_state = SessionState.SELECTING
        self.active_provider: ProviderConfig | None = None
        self.client: LLMClient | None = None
        self.summary_client: LLMClient | None = None
        self.agent: Agent | None = None
        self.reply_buffer = ""
        self.turn_start = 0.0
        self.timer: Timer | None = None
        self.stream_worker: Worker | None = None
        self.resume_worker: Worker | None = None
        self.command_worker: Worker | None = None
        self.active_session: ActiveSession | None = None
        self.session_screen_items: dict[str, SessionInfo] = {}
        self.spinner_index = 0
        self.current_iteration = 0
        self.max_iterations = 0
        self.task_usage = TokenUsage(0, 0)
        self.session_usage = TokenUsage(0, 0)
        self.task_usage_committed = False
        self.pending_permission_call_id = ""
        self.hook_worker: Worker | None = None
        self.hook_poll_timer: Timer | None = None
        self.task_poll_timer: Timer | None = None
        self.quitting = False

    def compose(self) -> ComposeResult:
        yield Static(render_banner(__version__, os.getcwd()), id="banner")
        yield Static("● 对话服务已就绪", id="ready")
        yield ConversationLog(id="conversation", wrap=True, highlight=False, markup=False)
        yield Static("", id="tool-activity", markup=False)
        yield Static("", id="streaming", markup=False)
        yield Static("", id="timer", markup=False)
        yield CommandCompletion(id="command-completion")
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
            yield Static("", id="task-status")
            yield Static("Tab 补全 · /help", id="command-hint")
            yield Static("", id="model-name")

    def on_mount(self) -> None:
        self.hook_poll_timer = self.set_interval(0.2, self._poll_hook_results)
        self.task_poll_timer = self.set_interval(0.1, self._poll_subagent_events)
        if len(self.config.providers) == 1:
            self._activate_provider(0)
            return

        self.session_state = SessionState.SELECTING
        self.push_screen(
            ProviderSelectScreen(self.config.providers),
            callback=self._provider_selected,
        )

    def on_unmount(self) -> None:
        """测试退出或终端关闭时也幂等释放会话文件。"""

        self.session_manager.close()

    def _provider_selected(self, selected_index: int | None) -> None:
        """选择完成后创建本次会话使用的 Provider。"""

        if selected_index is None:
            self.action_safe_quit()
            return
        self._activate_provider(selected_index)

    def _activate_provider(self, index: int) -> None:
        config = self.config.providers[index]
        self.active_provider = config
        self.client = self.client_factory(config)
        summary_config = replace(config, model=config.summary_model or config.model)
        self.summary_client = self.client_factory(summary_config)
        workdir = self.session_manager.project_root
        rule_store = RuleStore.load(workdir)
        self.active_session = self.session_manager.open_new(config.model)
        context_manager = ContextManager(
            workdir,
            session_id=self.active_session.session_id,
            summary_client=self.summary_client,
            context_window=config.context_window,
        )
        extra_read_roots = (
            [self.memory_manager.user_memory_dir] if self.memory_manager is not None else []
        )
        if self.skill_manager is not None:
            self.skill_runtime = self.skill_manager.create_runtime()
            skill_registry = registry_for_skill_tools(self.skill_manager.list_skills())
            system_registry = ToolRegistry()
            system_registry.register(LoadSkillTool(self.skill_manager, self.skill_runtime))
            self.task_manager = BackgroundTaskManager()
            subagent_tools = create_subagent_tools(self.agent_catalog, self.task_manager)
            self.subagent_tools = subagent_tools
            for tool in subagent_tools:
                system_registry.register(tool)
            self.registry = self.base_registry.combined(skill_registry, system_registry)
        else:
            self.task_manager = BackgroundTaskManager()
            system_registry = ToolRegistry()
            subagent_tools = create_subagent_tools(self.agent_catalog, self.task_manager)
            self.subagent_tools = subagent_tools
            for tool in subagent_tools:
                system_registry.register(tool)
            self.registry = self.base_registry.combined(system_registry)
        self.agent = Agent(
            self.client,
            self.active_session.conversation,
            self.registry,
            workdir,
            __version__,
            permission_engine=PermissionEngine(
                workdir,
                rule_store,
                sandbox=PathSandbox(workdir, extra_read_roots),
            ),
            approval_controller=ApprovalController(),
            permission_mode=rule_store.default_mode(),
            context_manager=context_manager,
            custom_instructions=self.custom_instructions,
            memory_manager=self.memory_manager,
            skill_manager=self.skill_manager,
            skill_runtime=self.skill_runtime,
            hook_engine=self.hook_engine,
            runtime_reminder_source=self.task_manager,
        )
        self.subagent_host = SubAgentHost(
            self.agent_catalog,
            self.task_manager,
            self.client_factory,
        )
        self.subagent_host.bind_parent(self.agent)
        for tool in subagent_tools:
            if isinstance(tool, (AgentTool, SendMessageTool)):
                tool.bind_host(self.subagent_host)
        if self.skill_manager is not None:
            self.skill_executor = SkillExecutor(
                self.skill_manager,
                self.agent,
                self.client_factory,
                subagent_host=self.subagent_host,
            )
        # SessionStart Hook 完成前暂不接受首条输入，避免首轮漏掉启动提醒。
        self.session_state = SessionState.COMMAND
        self._update_permission_mode_display()
        self._set_command_hint(True)
        self.query_one("#model-name", Static).update(self.client.model)
        self.query_one("#message-input", MessageInput).disabled = True
        self.hook_worker = self.run_worker(
            self._complete_activation(),
            name="hook-session-start",
            exclusive=False,
            exit_on_error=False,
        )

    async def _complete_activation(self) -> None:
        await self._trigger_lifecycle(HookEvent.SESSION_START)
        self.hook_worker = None
        self.session_state = SessionState.IDLE
        input_widget = self.query_one("#message-input", MessageInput)
        input_widget.disabled = False
        input_widget.focus()

    def on_message_input_submitted(self, event: MessageInput.Submitted) -> None:
        """接收输入框提交事件。"""

        if self.command_worker is not None:
            if event.value.strip().startswith("/"):
                self.show_message("上一条命令处理完成后再执行新命令。", error=True)
            return

        if self.session_state is not SessionState.IDLE:
            if event.value.strip().startswith("/"):
                self.show_message("当前任务结束或取消后再执行命令。", error=True)
            return

        text = event.value
        if not text.strip():
            return
        if text.strip().startswith("/"):
            self._clear_input()
            self._hide_completion()
            self.command_worker = self.run_worker(
                self._dispatch_slash_command(text),
                name="slash-command",
                exclusive=False,
                exit_on_error=False,
            )
            return

        self._start_turn(text)

    async def _dispatch_slash_command(self, text: str) -> None:
        try:
            await dispatch_command(text, self.command_registry, self)
        finally:
            # Textual 可能立即启动很快结束的 Worker。先让 run_worker 的返回值完成赋值，
            # 再清空引用，避免已完成的 Worker 被重新写回而永久误判为忙碌。
            await asyncio.sleep(0)
            self.command_worker = None

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """输入变化时刷新命令候选。"""

        if not isinstance(event.text_area, MessageInput):
            return
        text = event.text_area.text
        if self.completion_state.suppresses(text):
            self._hide_completion()
            return
        if (
            self.session_state is not SessionState.IDLE
            or "\n" in text
            or not text.startswith("/")
            or any(character.isspace() for character in text)
        ):
            self._hide_completion()
            return
        self.completion_state.update(self.command_registry.complete(text))
        self.query_one("#command-completion", CommandCompletion).show_state(self.completion_state)

    def move_completion(self, direction: int) -> bool:
        if not self.completion_state.active:
            return False
        if direction < 0:
            self.completion_state.move_up()
        else:
            self.completion_state.move_down()
        self.query_one("#command-completion", CommandCompletion).show_state(self.completion_state)
        return True

    def accept_completion(self) -> bool:
        """只填入选中命令；下一次 Enter 才真正提交。"""

        if not self.completion_state.active:
            return False
        selected = self.completion_state.selected()
        if selected is None:
            self._hide_completion()
            return False
        value = f"/{selected.name}"
        self.completion_state.accept(value)
        self.query_one("#command-completion", CommandCompletion).hide_menu()
        self.query_one("#message-input", MessageInput).load_text(value)
        return True

    def _hide_completion(self) -> None:
        self.completion_state.hide()
        try:
            self.query_one("#command-completion", CommandCompletion).hide_menu()
        except Exception:
            # compose 前的测试调用没有挂载 Widget。
            return

    def _start_turn(
        self,
        user_text: str,
        display_text: str | None = None,
        *,
        read_only: bool = False,
        skill_name: str = "",
        skill_arguments: str = "",
    ) -> None:
        """更新界面状态并启动异步模型请求。"""

        conversation = self.query_one("#conversation", RichLog)
        visible_text = display_text if display_text is not None else user_text
        conversation.write(Text(f"❯ {visible_text}", style="bold cyan"))

        input_widget = self.query_one("#message-input", MessageInput)
        input_widget.load_text("")
        input_widget.disabled = True
        self._hide_completion()
        self._set_command_hint(False)

        self.reply_buffer = ""
        self.turn_start = time.monotonic()
        self.spinner_index = 0
        self.current_iteration = 0
        self.max_iterations = 0
        self.task_usage = TokenUsage(0, 0)
        self.task_usage_committed = False
        self.session_state = SessionState.STREAMING
        self._clear_tool_activity()
        self.query_one("#streaming", Static).update("")
        self._update_timer()
        self.timer = self.set_interval(0.1, self._update_timer)
        if skill_name:
            event_source = self._consume_skill(skill_name, skill_arguments)
        else:
            event_source = self._consume_turn(user_text, read_only=read_only)
        self.stream_worker = self.run_worker(
            event_source,
            name="llm-stream",
            exclusive=True,
            exit_on_error=False,
        )

    async def _consume_turn(self, user_text: str, *, read_only: bool = False) -> None:
        """消费 Agent 事件并实时更新界面。"""

        if self.agent is None:
            self._finish_with_error(LLMError("unknown", "当前没有可用的 Provider。"))
            return

        await self._consume_event_stream(self.agent.run(user_text, read_only=read_only))

    async def _consume_skill(self, name: str, arguments: str) -> None:
        if self.skill_executor is None:
            self._finish_with_error(LLMError("unknown", "当前没有可用的 Skill 执行器。"))
            return
        await self._consume_event_stream(self.skill_executor.run_explicit(name, arguments))

    async def _consume_event_stream(self, events) -> None:
        """让普通 Agent 与 fork Skill 共用同一套 TUI 事件渲染。"""

        async for event in events:
            if event.type == "skill_start":
                self.query_one("#conversation", RichLog).write(
                    Text(f"● {event.text}", style="bold magenta")
                )
            elif event.type == "skill_end":
                self.query_one("#conversation", RichLog).write(
                    Text(f"● {event.text}", style="bold green")
                )
            elif event.type == "skill_warning":
                self.query_one("#conversation", RichLog).write(
                    Text(f"● Skill 警告：{event.text}", style="bold yellow")
                )
            elif event.type == "hook" and event.hook_execution is not None:
                self._write_hook_execution(event.hook_execution)
            elif event.type == "progress":
                self.current_iteration = event.iteration
                self.max_iterations = event.max_iterations
                self._update_timer()
            elif event.type == "text":
                self.reply_buffer += event.text
                self.query_one("#streaming", Static).update(self.reply_buffer)
            elif event.type == "tool_start" and event.tool_call is not None:
                self._flush_streaming_text()
                self._start_tool_display(f"main:{event.tool_call.id}", event.tool_call)
            elif event.type == "tool_end" and event.tool_result is not None:
                self._finish_tool_display(f"main:{event.tool_result.call_id}", event.tool_result)
            elif event.type == "permission_request" and event.permission_request is not None:
                self._show_permission_request(event.permission_request)
            elif event.type in {"permission_warning", "context_warning", "session_warning"}:
                self.query_one("#conversation", RichLog).write(
                    Text(f"● {event.text}", style="bold yellow")
                )
            elif event.type == "compact" and event.compact is not None:
                self._write_compact_event(event.compact)
            elif event.type == "usage" and event.usage is not None:
                self.task_usage = event.usage
                self._update_usage_status(event.usage, task_in_progress=True)
            elif event.type == "completed":
                self._finish_with_reply(event.text, event.usage)
            elif event.type == "cancelled":
                self._finish_with_status(event.text, "bold yellow", event.usage)
            elif event.type == "limit":
                self._finish_with_status(event.text, "bold yellow", event.usage)
            elif event.type == "user_rejected":
                self._finish_with_status(
                    f"输入被 Hook 拒绝：{event.text}",
                    "bold red",
                    event.usage,
                )
                self.query_one("#message-input", MessageInput).load_text(event.rejected_text)
            elif event.type == "error":
                error = event.error
                if isinstance(error, LLMError):
                    self._finish_with_error(error, event.usage)
                else:
                    self._finish_with_error(
                        LLMError("unknown", "模型请求失败，请稍后再试。"),
                        event.usage,
                    )

    def _write_hook_execution(self, execution: HookExecution) -> None:
        """以简短且可区分的样式显示 Hook 状态。"""

        if execution.blocked or execution.status == "failed":
            style = "bold red"
        elif execution.status in {"timeout", "not_implemented", "scheduled"}:
            style = "bold yellow"
        else:
            style = "magenta"
        message = execution.message or execution.status
        self.query_one("#conversation", RichLog).write(
            Text(f"● Hook {execution.hook_name}：{message}", style=style)
        )

    async def _trigger_lifecycle(
        self,
        event: HookEvent,
        data: dict[str, object] | None = None,
    ) -> None:
        if self.agent is None:
            return
        for agent_event in await self.agent.trigger_hook_event(event, data):
            if agent_event.hook_execution is not None:
                self._write_hook_execution(agent_event.hook_execution)

    def _poll_hook_results(self) -> None:
        """轻量轮询已完成异步 Hook，不阻塞 Textual。"""

        for execution in self.hook_engine.drain_background_results():
            self._write_hook_execution(execution)

    def _poll_subagent_events(self) -> None:
        """显示子任务状态；后台内部对话不会写入主 scrollback。"""

        if self.task_manager is None:
            return
        for event in self.task_manager.drain_events():
            self._write_subagent_event(event)
        self._update_task_status()

    def _write_subagent_event(self, event: SubAgentEvent) -> None:
        conversation = self.query_one("#conversation", RichLog)
        label = event.task_name or event.agent_name or event.task_id
        if event.attached and event.type == "text":
            current = self.subagent_buffers.get(event.task_id, "") + event.text
            self.subagent_buffers[event.task_id] = current
            self.query_one("#streaming", Static).update(f"[{label}] {current}")
            return
        if event.attached and event.type == "tool_start" and event.tool_call is not None:
            self._flush_subagent_buffer(event.task_id, label)
            self._start_tool_display(
                f"sub:{event.task_id}:{event.tool_call.id}",
                event.tool_call,
                agent_label=label,
            )
            return
        if event.attached and event.type == "tool_end" and event.tool_result is not None:
            self._finish_tool_display(
                f"sub:{event.task_id}:{event.tool_result.call_id}",
                event.tool_result,
                agent_label=label,
            )
            return
        if event.attached and event.type == "progress":
            conversation.write(
                Text(
                    f"● Agent  {label}  第 {event.iteration}/{event.max_iterations} 轮",
                    style=TOOL_MUTED,
                )
            )
            return
        if event.type == "queued":
            conversation.write(Text(f"● Agent  {label}  已排队", style=TOOL_MUTED))
        elif event.type == "workspace_warning":
            conversation.write(Text(f"● Agent  {label}  {event.text}", style=TOOL_ERROR))
        elif event.type == "running":
            mode = "前台" if event.attached else "后台"
            conversation.write(Text(f"● Agent  {label}  {mode}运行", style=TOOL_ACCENT))
        elif event.type in {"manual_background", "timeout_background"}:
            reason = "用户切换" if event.type == "manual_background" else "运行超过 120 秒"
            self._clear_tool_activity(prefix=f"sub:{event.task_id}:")
            conversation.write(Text(f"● Agent  {label}  已转后台 · {reason}", style=TOOL_MUTED))
        elif event.type in {"completed", "failed", "cancelled"} and event.status in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }:
            self._flush_subagent_buffer(event.task_id, label)
            self._clear_tool_activity(prefix=f"sub:{event.task_id}:")
            summary = event.text.replace("\n", " ")
            # 中文字符通常占两个终端单元；40 字约等于 80 个显示宽度。
            if len(summary) > 40:
                summary = summary[:37] + "..."
            suffix = f" · {summary}" if summary else ""
            if event.status is TaskStatus.COMPLETED:
                conversation.write(Text(f"✓ Agent  {label}  已完成{suffix}", style=TOOL_MUTED))
            elif event.status is TaskStatus.CANCELLED:
                conversation.write(Text(f"● Agent  {label}  已取消", style=TOOL_MUTED))
            else:
                conversation.write(
                    Group(
                        Text(f"✗ Agent  {label}  执行失败", style=TOOL_ERROR),
                        Text(
                            f"  └ {summary or '子 Agent 未正常完成'} · {event.task_id}",
                            style=TOOL_ERROR,
                        ),
                    )
                )

    def _flush_subagent_buffer(self, task_id: str, label: str) -> None:
        text = self.subagent_buffers.pop(task_id, "")
        if not text:
            return
        self.query_one("#conversation", RichLog).write(
            Group(Text(f"[{label}]", style=TOOL_ACCENT), Markdown(text))
        )
        self.query_one("#streaming", Static).update("")

    def _update_task_status(self) -> None:
        try:
            widget = self.query_one("#task-status", Static)
        except Exception:
            return
        if self.task_manager is None:
            widget.update("")
            return
        running = self.task_manager.running_count()
        queued = self.task_manager.queued_count()
        widget.update(f"Agents {running} running · {queued} queued" if running or queued else "")

    def _start_manual_compact(self) -> None:
        """在空闲状态启动一次不进入普通对话的强制压缩。"""

        self.query_one("#conversation", RichLog).write(Text("❯ /compact", style="bold cyan"))
        input_widget = self.query_one("#message-input", MessageInput)
        input_widget.load_text("")
        input_widget.disabled = True
        self._hide_completion()
        self._set_command_hint(False)
        self.turn_start = time.monotonic()
        self.spinner_index = 0
        self.current_iteration = 0
        self.max_iterations = 0
        self.task_usage = TokenUsage(0, 0)
        self.task_usage_committed = False
        self.session_state = SessionState.STREAMING
        self._update_timer()
        self.timer = self.set_interval(0.1, self._update_timer)
        self.stream_worker = self.run_worker(
            self._consume_manual_compact(),
            name="context-compact",
            exclusive=True,
            exit_on_error=False,
        )

    async def _consume_manual_compact(self) -> None:
        if self.agent is None:
            self._finish_with_error(LLMError("unknown", "当前没有可用的 Provider。"))
            return
        try:
            async for event in self.agent.compact_context():
                if event.type == "session_warning":
                    self.query_one("#conversation", RichLog).write(
                        Text(f"● {event.text}", style="bold yellow")
                    )
                if event.compact is not None:
                    self._write_compact_event(event.compact)
        except asyncio.CancelledError:
            self._finish_with_status("上下文压缩已取消。", "bold yellow")
            return
        self._stop_turn()

    def _write_compact_event(self, event) -> None:
        """把压缩过程转换为可观察且不泄露内部 Prompt 的状态行。"""

        if event.phase == "auto_start":
            text = f"● 正在压缩上下文…（约 {event.before_tokens} Token）"
            style = "bold cyan"
        elif event.phase in {"auto_complete", "manual_complete"}:
            text = f"● 上下文压缩完成：{event.before_tokens} → {event.after_tokens} Token"
            style = "bold green"
        elif event.phase in {"auto_failed", "manual_failed"}:
            text = f"● 上下文压缩失败：{event.message or '未知原因'}"
            style = "bold yellow"
        else:
            text = f"● {event.message or '自动上下文压缩已熔断。'}"
            style = "bold yellow"
        self.query_one("#conversation", RichLog).write(Text(text, style=style))

    @staticmethod
    def _render_tool_line(
        pending: PendingToolDisplay,
        symbol: str,
        *,
        summary: str = "",
        style: str = TOOL_MUTED,
        active: bool = False,
    ) -> Text:
        """分段渲染一条工具记录，让参数始终保持低调。"""

        line = Text(f"{symbol} ", style=style)
        if pending.agent_label:
            line.append(f"{pending.agent_label} · ", style=TOOL_MUTED)
        line.append(pending.call.name, style=TOOL_ACCENT if active else style)
        key = _tool_key_argument(pending.call)
        if key:
            line.append(f"  {key}", style=TOOL_MUTED if active else style)
        if summary:
            line.append(f"  {summary}", style=style)
        return line

    def _start_tool_display(
        self,
        key: str,
        call: ToolCall,
        *,
        agent_label: str = "",
    ) -> None:
        """工具开始时只更新动态区，不提前污染 scrollback。"""

        self.active_tool_displays[key] = PendingToolDisplay(key, call, agent_label)
        self._update_tool_activity()

    def _finish_tool_display(
        self,
        key: str,
        result: ToolResult,
        *,
        agent_label: str = "",
    ) -> None:
        """工具结束后移除动态项，并把最终状态定型到历史区。"""

        pending = self.active_tool_displays.pop(key, None)
        if pending is None:
            pending = PendingToolDisplay(
                key,
                ToolCall(result.call_id, result.tool_name, {}),
                agent_label,
            )
        self._update_tool_activity()
        conversation = self.query_one("#conversation", RichLog)
        summary = format_tool_result(result)
        if result.success:
            conversation.write(self._render_tool_line(pending, "✓", summary=summary))
            return
        if result.error_code == "cancelled":
            conversation.write(self._render_tool_line(pending, "●", summary=f"已取消 · {summary}"))
            return
        conversation.write(
            Group(
                self._render_tool_line(pending, "✗", style=TOOL_ERROR),
                Text(f"  └ {summary}", style=TOOL_ERROR),
            )
        )

    def _update_tool_activity(self) -> None:
        """按发起顺序刷新全部正在运行的工具。"""

        try:
            widget = self.query_one("#tool-activity", Static)
        except Exception:
            # CLI finally 或未挂载的测试对象也会调用清理。
            return
        if not self.active_tool_displays:
            widget.update("")
            return
        lines = [
            self._render_tool_line(pending, "●", style=TOOL_ACCENT, active=True)
            for pending in self.active_tool_displays.values()
        ]
        widget.update(Group(*lines))

    def _clear_tool_activity(self, *, prefix: str = "") -> None:
        """清理指定任务或整个回合遗留的动态工具。"""

        if prefix:
            keys = [key for key in self.active_tool_displays if key.startswith(prefix)]
            for key in keys:
                self.active_tool_displays.pop(key, None)
        else:
            self.active_tool_displays.clear()
        self._update_tool_activity()

    def _write_tool_result(self, result: ToolResult) -> None:
        """兼容直接写入结果的调用方和既有测试。"""

        self._finish_tool_display(f"main:{result.call_id}", result)

    def _flush_streaming_text(self) -> None:
        """把工具调用前的模型文字固定到历史区。"""

        if not self.reply_buffer:
            return
        self.query_one("#conversation", RichLog).write(Markdown(self.reply_buffer))
        self.reply_buffer = ""
        self.query_one("#streaming", Static).update("")

    def _update_timer(self) -> None:
        """刷新等待动画和已用秒数。"""

        if self.session_state not in {SessionState.STREAMING, SessionState.APPROVING}:
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
        self._clear_tool_activity()
        self.query_one("#streaming", Static).update("")
        self.query_one("#timer", Static).update("")

        input_widget = self.query_one("#message-input", MessageInput)
        input_widget.disabled = False
        input_widget.focus()
        self._set_command_hint(True)
        # 权限 Modal 可能也在本轮刷新中关闭；下一次刷新后再聚焦，避免焦点被弹窗覆盖。
        self.call_after_refresh(input_widget.focus)
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
        error: LLMError,
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
        self._update_permission_mode_display()
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
        self._update_permission_mode_display()
        self._start_turn(DO_PLAN_PROMPT, display_text="/do")

    def _show_permission_request(self, request: PermissionRequest) -> None:
        """打开权限确认框，Agent 会等待回调结果。"""

        self.session_state = SessionState.APPROVING
        self.pending_permission_call_id = request.call.id
        self.push_screen(
            PermissionApprovalScreen(request),
            callback=self._permission_selected,
        )

    def _permission_selected(self, choice: ApprovalChoice | None) -> None:
        """把确认框选择交还 Agent，取消则停止当前任务。"""

        if self.agent is None:
            return
        call_id = self.pending_permission_call_id
        self.pending_permission_call_id = ""
        self.session_state = SessionState.STREAMING
        if choice is None:
            self.agent.request_cancel()
            return
        self.agent.resolve_permission(call_id, choice)

    def action_cycle_permission_mode(self) -> None:
        """空闲时按 Shift+Tab 循环切换四种权限模式。"""

        if self.session_state is not SessionState.IDLE or self.agent is None:
            return
        self.agent.cycle_permission_mode()
        self._update_permission_mode_display()

    def action_submit_current_input(self) -> None:
        """按会话状态处理 Enter，不依赖焦点是否从 Modal 正确返回。"""

        if self.completion_state.active and self.accept_completion():
            return
        if self.session_state is SessionState.SELECTING and isinstance(
            self.screen, ProviderSelectScreen
        ):
            self.screen.submit_highlighted()
            return
        if self.session_state is SessionState.APPROVING and isinstance(
            self.screen, PermissionApprovalScreen
        ):
            self.screen.submit_highlighted()
            return
        if self.session_state is SessionState.RESUMING and isinstance(
            self.screen, SessionResumeScreen
        ):
            self.screen.submit_highlighted()
            return
        command_screens = (
            CommandHelpScreen,
            SessionCommandScreen,
            MemoryCommandScreen,
            PermissionModeScreen,
            ReviewTargetScreen,
            ConfirmCommandScreen,
        )
        if isinstance(self.screen, command_screens):
            self.screen.submit_highlighted()
            return
        if self.session_state is not SessionState.IDLE:
            return
        input_widget = self.query_one("#message-input", MessageInput)
        self.on_message_input_submitted(MessageInput.Submitted(input_widget.text))

    def _update_permission_mode_display(self) -> None:
        """让状态栏和就绪提示始终使用 Agent 的唯一模式状态。"""

        if self.agent is None:
            return
        mode = self.agent.mode
        provider = self.active_provider.name if self.active_provider is not None else ""
        self.query_one("#provider-name", Static).update(f"{provider} · {mode.value}")
        messages = {
            PermissionMode.DEFAULT: "● Default：写文件和命令需要确认",
            PermissionMode.ACCEPT_EDITS: "● Accept Edits：文件修改自动允许",
            PermissionMode.PLAN: "● Plan Mode：仅使用只读工具",
            PermissionMode.BYPASS_PERMISSIONS: "● Bypass：日常操作自动允许，硬防线仍生效",
        }
        self.query_one("#ready", Static).update(messages[mode])

    def _clear_input(self) -> None:
        self.query_one("#message-input", MessageInput).load_text("")

    # 下列方法组成 CommandUI：命令层只调用这些高层能力。
    def is_idle(self) -> bool:
        return self.session_state is SessionState.IDLE

    def show_message(self, text: str, *, error: bool = False) -> None:
        style = "bold red" if error else "cyan"
        self.query_one("#conversation", RichLog).write(Text(f"● {text}", style=style))

    def open_help(self, commands: list[Command]) -> None:
        self.query_one("#conversation", RichLog).write(Text("❯ /help", style="bold cyan"))
        self.push_screen(CommandHelpScreen(commands))

    def get_status(self) -> CommandStatus:
        messages = self.agent.conversation.get_messages() if self.agent is not None else []
        estimated = sum(estimate_message_tokens(message) for message in messages)
        builtin_count, mcp_count = self.registry.counts()
        user_memories = 0
        project_memories = 0
        if self.memory_manager is not None:
            try:
                user_memories, project_memories = self.memory_manager.memory_counts()
            except OSError:
                pass
        provider = self.active_provider.name if self.active_provider is not None else "未知"
        model = self.client.model if self.client is not None else "未知"
        mode = self.agent.mode.value if self.agent is not None else "未知"
        session_id = self.active_session.session_id if self.active_session is not None else "未知"
        return CommandStatus(
            version=__version__,
            cwd=str(self.session_manager.project_root),
            provider=provider,
            model=model,
            permission_mode=mode,
            session_id=session_id,
            input_tokens=self.session_usage.input_tokens,
            output_tokens=self.session_usage.output_tokens,
            cache_write_tokens=self.session_usage.cache_write_tokens,
            cache_read_tokens=self.session_usage.cache_read_tokens,
            estimated_context_tokens=estimated,
            builtin_tool_count=builtin_count,
            mcp_tool_count=mcp_count,
            user_memory_count=user_memories,
            project_memory_count=project_memories,
        )

    def quit(self) -> None:
        self.action_safe_quit()

    def force_compact(self) -> None:
        self._start_manual_compact()

    def clear_session(self) -> None:
        self._begin_local_command("/clear")
        self.resume_worker = self.run_worker(
            self._clear_current_session(),
            name="clear-session",
            exclusive=True,
            exit_on_error=False,
        )

    def enter_plan_mode(self) -> None:
        self._enter_plan_mode()

    def execute_plan(self) -> None:
        self._execute_plan()

    def open_sessions(self, *, resume_only: bool = False) -> None:
        if resume_only:
            self._show_resume_screen()
        else:
            self._show_session_manager()

    def open_memories(self) -> None:
        if self.memory_manager is None:
            self.show_message("当前没有可用的记忆管理器。", error=True)
            return
        self._begin_local_command("/memory")
        self.resume_worker = self.run_worker(
            self._load_memory_screen(),
            name="memory-list",
            exclusive=True,
            exit_on_error=False,
        )

    def open_permissions(self) -> None:
        if self.agent is None:
            self.show_message("当前没有可用的 Agent。", error=True)
            return
        self._begin_local_command("/permission")
        self.push_screen(
            PermissionModeScreen(self.agent.mode),
            callback=self._permission_mode_selected,
        )

    def open_review(self) -> None:
        self._begin_local_command("/review")
        self.push_screen(ReviewTargetScreen(), callback=self._review_target_selected)

    def open_skills(self) -> None:
        self._begin_local_command("/skill")
        skills, issues = self.skill_items()
        self.push_screen(
            SkillManagementScreen(skills, issues),
            callback=self._skill_screen_closed,
        )

    def hook_items(self):
        return list(self.hook_engine.snapshot.hooks), list(self.hook_engine.snapshot.issues)

    def skill_items(self):
        if self.skill_manager is None:
            return [], []
        return self.skill_manager.list_skills(), self.skill_manager.issues()

    def reload_skills(self):
        if self.skill_manager is None:
            return [], []
        snapshot = self.skill_manager.reload()
        from dragon_code.command import create_skill_commands

        self.command_registry.replace_source(
            "skill",
            create_skill_commands(snapshot.skills),
        )
        if self.agent is not None and self.skill_runtime is not None:
            skill_registry = registry_for_skill_tools(snapshot.skills)
            system_registry = ToolRegistry()
            system_registry.register(LoadSkillTool(self.skill_manager, self.skill_runtime))
            for tool in self.subagent_tools:
                system_registry.register(tool)
            self.registry = self.base_registry.combined(skill_registry, system_registry)
            self.agent.registry = self.registry
            self.agent.plan_registry = self.registry.restricted({"Read", "Glob", "Grep"})
        return list(snapshot.skills), list(snapshot.issues)

    def _skill_screen_closed(self, result: SkillScreenResult | None) -> None:
        if result is not None and result.action == "reload":
            skills, issues = self.reload_skills()
            self.show_message(f"Skill 已重新加载：{len(skills)} 个有效，{len(issues)} 个问题。")
        self._finish_local_command()

    def run_skill(self, name: str, arguments: str = "") -> None:
        if self.skill_manager is None or self.agent is None:
            self.show_message("当前没有可用的 Skill。", error=True)
            return
        skill = self.skill_manager.get(name)
        if skill is None:
            self.show_message(f"未知 Skill：{name}", error=True)
            return
        if name == "review" and not arguments.strip():
            self.open_review()
            return
        display = f"/{name}" + (f" {arguments}" if arguments else "")
        self._start_turn(
            f"执行 Skill：{name}",
            display_text=display,
            skill_name=name,
            skill_arguments=arguments,
        )

    def _set_command_hint(self, visible: bool) -> None:
        try:
            self.query_one("#command-hint", Static).display = visible
        except Exception:
            return

    def _begin_local_command(self, label: str) -> None:
        self.query_one("#conversation", RichLog).write(Text(f"❯ {label}", style="bold cyan"))
        self.session_state = SessionState.COMMAND
        input_widget = self.query_one("#message-input", MessageInput)
        input_widget.load_text("")
        input_widget.disabled = True
        self._hide_completion()
        self._set_command_hint(False)

    def _finish_local_command(self, error: str = "") -> None:
        self.resume_worker = None
        self.session_state = SessionState.IDLE
        input_widget = self.query_one("#message-input", MessageInput)
        input_widget.disabled = False
        input_widget.focus()
        self._set_command_hint(True)
        if error:
            self.show_message(error, error=True)

    async def _clear_current_session(self) -> None:
        if self.agent is None or self.client is None or self.summary_client is None:
            self._finish_local_command("当前没有可用的 Provider。")
            return
        new_session: ActiveSession | None = None
        try:
            new_session = await asyncio.to_thread(
                self.session_manager.open_new,
                self.client.model,
            )
            context_manager = ContextManager(
                self.session_manager.project_root,
                session_id=new_session.session_id,
                summary_client=self.summary_client,
                context_window=self.client.config.context_window,
            )
            old_session = self.active_session
            await self._trigger_lifecycle(HookEvent.SESSION_END, {"reason": "clear"})
            await self._reset_subagents()
            await self.hook_engine.close()
            self.agent.replace_session(
                new_session.conversation,
                context_manager,
                preserve_mode=True,
            )
            self.active_session = new_session
            await self._trigger_lifecycle(HookEvent.SESSION_START, {"reason": "clear"})
            self.session_usage = TokenUsage(0, 0)
            self.task_usage = TokenUsage(0, 0)
            self._update_usage_status(self.session_usage)
            self.query_one("#conversation", RichLog).clear()
            self.show_message(f"已开始新会话 {new_session.session_id}。")
            if old_session is not None:
                old_session.writer.close()
            self._update_permission_mode_display()
            self._finish_local_command()
        except asyncio.CancelledError:
            if new_session is not None:
                new_session.writer.close()
            self._finish_local_command("新建会话已取消。")
        except Exception as error:
            if new_session is not None:
                new_session.writer.close()
            self._finish_local_command(f"新建会话失败：{error}")

    def _show_help(self) -> None:
        """兼容旧测试入口，帮助内容仍由注册中心提供。"""

        self.open_help(self.command_registry.visible())

    def action_safe_quit(self) -> None:
        """先触发会话结束 Hook，再清理资源并退出。"""

        if self.quitting:
            return
        self.quitting = True
        if self.agent is not None:
            self.agent.request_cancel()
        if self.skill_executor is not None:
            self.skill_executor.request_cancel()
        self.hook_worker = self.run_worker(
            self._quit_after_hooks(),
            name="hook-session-end",
            exclusive=False,
            exit_on_error=False,
        )

    async def _quit_after_hooks(self) -> None:
        try:
            await self._trigger_lifecycle(HookEvent.SESSION_END, {"reason": "exit"})
        finally:
            await self.close_subagents()
            await self.hook_engine.close()
            self._perform_safe_quit()

    def _perform_safe_quit(self) -> None:
        """清理计时器和现有 Worker，恢复终端。"""

        if self.timer is not None:
            self.timer.stop()
            self.timer = None
        if self.agent is not None:
            self.agent.request_cancel()
        if self.skill_executor is not None:
            self.skill_executor.request_cancel()
        if self.stream_worker is not None:
            self.stream_worker.cancel()
            self.stream_worker = None
        if self.resume_worker is not None:
            self.resume_worker.cancel()
            self.resume_worker = None
        if self.command_worker is not None:
            self.command_worker.cancel()
            self.command_worker = None
        if self.active_session is not None:
            self.active_session.writer.close()
        self.exit()

    def action_cancel_turn(self) -> None:
        """Esc 只取消正在运行的 Agent，不退出应用。"""

        if self.completion_state.active:
            self._hide_completion()
            return
        if isinstance(
            self.screen,
            (
                CommandHelpScreen,
                SessionCommandScreen,
                MemoryCommandScreen,
                PermissionModeScreen,
                ReviewTargetScreen,
                SkillManagementScreen,
                ConfirmCommandScreen,
            ),
        ):
            self.screen.action_cancel()
            return
        if (
            self.session_state
            in {
                SessionState.STREAMING,
                SessionState.APPROVING,
            }
            and self.agent is not None
        ):
            self.agent.request_cancel()
            if self.skill_executor is not None:
                self.skill_executor.request_cancel()
        elif self.session_state is SessionState.RESUMING:
            if isinstance(self.screen, SessionResumeScreen):
                self.screen.dismiss(None)
            elif self.resume_worker is not None:
                self.resume_worker.cancel()
                self._finish_resume()
        elif self.session_state is SessionState.COMMAND:
            if self.resume_worker is not None:
                self.resume_worker.cancel()
            self._finish_local_command()

    def action_background_current_subagent(self) -> None:
        """Ctrl+B 只解除前台等待，底层子 Agent 继续同一次运行。"""

        if self.task_manager is None:
            return
        task_id = self.task_manager.move_foreground_to_background()
        if task_id is None:
            self.show_message("当前没有可转入后台的前台子 Agent。")

    async def _reset_subagents(self) -> None:
        if self.task_manager is not None:
            await self.task_manager.reset_session()
        if self.subagent_host is not None:
            await self.subagent_host.reset_sessions()
        self.subagent_buffers.clear()
        self._clear_tool_activity()
        self._update_task_status()

    async def close_subagents(self) -> None:
        """供 TUI 正常退出和 CLI finally 幂等清理子任务。"""

        if self.task_manager is not None:
            await self.task_manager.close()
        if self.subagent_host is not None:
            await self.subagent_host.close()
        self.subagent_buffers.clear()
        self._clear_tool_activity()

    def action_copy_or_quit(self) -> None:
        """有选中文字时复制，否则沿用 Ctrl+C 安全退出。"""

        selected_text = self.screen.get_selected_text()
        if selected_text:
            self.copy_to_clipboard(selected_text)
            return

        if self.session_state in {
            SessionState.STREAMING,
            SessionState.APPROVING,
            SessionState.RESUMING,
            SessionState.COMMAND,
        }:
            self.action_cancel_turn()
            return

        self.action_safe_quit()

    def _show_resume_screen(self) -> None:
        """异步扫描会话，避免目录较大时冻结 Textual。"""

        self._clear_input()
        self.query_one("#conversation", RichLog).write(Text("❯ /resume", style="bold cyan"))
        self.session_state = SessionState.RESUMING
        self.query_one("#message-input", MessageInput).disabled = True
        self._hide_completion()
        self._set_command_hint(False)
        self.resume_worker = self.run_worker(
            self._load_session_list(),
            name="session-list",
            exclusive=True,
            exit_on_error=False,
        )

    async def _load_session_list(self) -> None:
        try:
            sessions = await asyncio.to_thread(self.session_manager.list_sessions)
        except Exception:
            self.query_one("#conversation", RichLog).write(
                Text("● 无法读取历史会话列表。", style="bold yellow")
            )
            self._finish_resume()
            return
        if not sessions:
            self.query_one("#conversation", RichLog).write(
                Text("● 当前项目还没有可恢复的会话。", style="dim")
            )
            self._finish_resume()
            return
        self.resume_worker = None
        self.push_screen(SessionResumeScreen(sessions), callback=self._resume_selected)

    def _resume_selected(self, session_id: str | None) -> None:
        if session_id is None:
            self._finish_resume()
            return
        self.resume_worker = self.run_worker(
            self._restore_session(session_id),
            name="session-restore",
            exclusive=True,
            exit_on_error=False,
        )

    async def _restore_session(self, session_id: str) -> None:
        """准备完整新对象后再切换，失败时保留旧会话。"""

        if self.client is None or self.summary_client is None or self.agent is None:
            self._finish_resume("当前没有可用的 Provider。")
            return
        new_session: ActiveSession | None = None
        try:
            new_session = await asyncio.to_thread(
                self.session_manager.restore,
                session_id,
                self.client.model,
            )
            context_manager = ContextManager(
                self.session_manager.project_root,
                session_id=session_id,
                summary_client=self.summary_client,
                context_window=self.client.config.context_window,
            )
            system = await build_system_prompt(
                self.session_manager.project_root,
                __version__,
                self.client.model,
                custom_instructions=self.custom_instructions,
                memory=self.memory_manager.current_index() if self.memory_manager else "",
            )
            history = new_session.conversation.get_messages()
            if context_manager.restored_history_needs_compaction(
                history,
                system,
                self.registry.definitions(),
            ):
                outcome = await context_manager.compact_restored_history(history)
                if not outcome.success:
                    raise RuntimeError("恢复历史超过模型窗口，自动压缩失败")
                new_session.conversation.replace_messages(outcome.history)

            old_session = self.active_session
            await self._trigger_lifecycle(HookEvent.SESSION_END, {"reason": "resume"})
            await self._reset_subagents()
            await self.hook_engine.close()
            self.agent.replace_session(new_session.conversation, context_manager)
            self.active_session = new_session
            await self._trigger_lifecycle(HookEvent.SESSION_RESUME, {"reason": "resume"})
            if old_session is not None:
                old_session.writer.close()

            self.session_usage = TokenUsage(0, 0)
            self._update_usage_status(self.session_usage)
            self._update_permission_mode_display()
            notice = f"● 已恢复会话 {session_id}，共 {new_session.restored_count} 条消息。"
            self.query_one("#conversation", RichLog).write(Text(notice, style="bold green"))
            for item in new_session.restore_notices:
                self.query_one("#conversation", RichLog).write(
                    Text(f"● {item}", style="bold yellow")
                )
            self._finish_resume()
        except asyncio.CancelledError:
            if new_session is not None:
                new_session.writer.close()
            self._finish_resume()
        except Exception as error:
            if new_session is not None:
                new_session.writer.close()
            self._finish_resume(f"恢复失败：{error}")

    def _finish_resume(self, error: str = "") -> None:
        self.resume_worker = None
        self.session_state = SessionState.IDLE
        input_widget = self.query_one("#message-input", MessageInput)
        input_widget.disabled = False
        input_widget.focus()
        self._set_command_hint(True)
        if error:
            self.query_one("#conversation", RichLog).write(Text(f"● {error}", style="bold red"))

    def _show_session_manager(self) -> None:
        """扫描并打开会话管理界面。"""

        self.query_one("#conversation", RichLog).write(Text("❯ /session", style="bold cyan"))
        self.session_state = SessionState.RESUMING
        self.query_one("#message-input", MessageInput).disabled = True
        self._hide_completion()
        self._set_command_hint(False)
        self.resume_worker = self.run_worker(
            self._load_session_manager(),
            name="session-manager-list",
            exclusive=True,
            exit_on_error=False,
        )

    async def _load_session_manager(self) -> None:
        try:
            sessions = await asyncio.to_thread(self.session_manager.list_sessions)
        except Exception:
            self._finish_resume("无法读取历史会话列表。")
            return
        if not sessions:
            self._finish_resume("当前项目还没有历史会话。")
            return
        self.session_screen_items = {item.session_id: item for item in sessions}
        self.resume_worker = None
        active_id = self.active_session.session_id if self.active_session is not None else ""
        self.push_screen(
            SessionCommandScreen(sessions, active_id, resume_only=False),
            callback=self._session_command_selected,
        )

    def _session_command_selected(self, result: SessionScreenResult | None) -> None:
        if result is None:
            self._finish_resume()
            return
        if result.action == "resume":
            self._resume_selected(result.session_id)
            return
        info = self.session_screen_items.get(result.session_id)
        if info is None:
            self._finish_resume("目标会话已经不存在。")
            return
        if self.active_session is not None and result.session_id == self.active_session.session_id:
            self._finish_resume("不能删除当前会话。")
            return
        target = f"标题：{info.title}\n会话 ID：{info.session_id}"
        self.push_screen(
            ConfirmCommandScreen("永久删除这个会话？", target),
            callback=lambda confirmed: self._session_delete_confirmed(
                result.session_id,
                confirmed,
            ),
        )

    def _session_delete_confirmed(self, session_id: str, confirmed: bool) -> None:
        if not confirmed:
            self._finish_resume()
            return
        self.resume_worker = self.run_worker(
            self._delete_session(session_id),
            name="session-delete",
            exclusive=True,
            exit_on_error=False,
        )

    async def _delete_session(self, session_id: str) -> None:
        active_id = self.active_session.session_id if self.active_session is not None else ""
        try:
            await asyncio.to_thread(self.session_manager.delete, session_id, active_id)
            self.show_message(f"已删除会话 {session_id}。")
            await self._load_session_manager()
        except asyncio.CancelledError:
            self._finish_resume("删除会话已取消。")
        except Exception as error:
            self._finish_resume(f"删除会话失败：{error}")

    async def _load_memory_screen(self) -> None:
        if self.memory_manager is None:
            self._finish_local_command("当前没有可用的记忆管理器。")
            return
        try:
            memories = await asyncio.to_thread(self.memory_manager.list_memories)
        except Exception:
            self._finish_local_command("无法读取长期记忆。")
            return
        self.resume_worker = None
        self.push_screen(MemoryCommandScreen(memories), callback=self._memory_selected)

    def _memory_selected(self, result: MemoryScreenResult | None) -> None:
        if result is None:
            self._finish_local_command()
            return
        item = result.memory
        if result.action == "view":
            text = (
                f"记忆：{item.title}\n层级：{item.level}\n类型：{item.memory_type}\n"
                f"文件：{item.filename}\n\n{item.content}"
            )
            self.show_message(text)
            self._finish_local_command()
            return
        target = f"层级：{item.level}\n标题：{item.title}\n文件：{item.filename}"
        self.push_screen(
            ConfirmCommandScreen("永久删除这条记忆？", target),
            callback=lambda confirmed: self._memory_delete_confirmed(item, confirmed),
        )

    def _memory_delete_confirmed(self, item: MemoryInfo, confirmed: bool) -> None:
        if not confirmed:
            self._finish_local_command()
            return
        self.resume_worker = self.run_worker(
            self._delete_memory(item),
            name="memory-delete",
            exclusive=True,
            exit_on_error=False,
        )

    async def _delete_memory(self, item: MemoryInfo) -> None:
        if self.memory_manager is None:
            self._finish_local_command("当前没有可用的记忆管理器。")
            return
        try:
            await self.memory_manager.delete_memory(item.level, item.filename)
            self.show_message(f"已删除记忆“{item.title}”。")
            await self._load_memory_screen()
        except asyncio.CancelledError:
            self._finish_local_command("删除记忆已取消。")
        except Exception as error:
            self._finish_local_command(f"删除记忆失败：{error}")

    def _permission_mode_selected(self, mode: PermissionMode | None) -> None:
        if mode is not None and self.agent is not None:
            self.agent.set_permission_mode(mode)
            self._update_permission_mode_display()
            self.show_message(f"权限模式已切换为 {mode.value}。")
        self._finish_local_command()

    def _review_target_selected(self, target: str | None) -> None:
        if target is None:
            self._finish_local_command()
            return
        self.resume_worker = self.run_worker(
            self._prepare_review(target),
            name="review-prepare",
            exclusive=True,
            exit_on_error=False,
        )

    async def _prepare_review(self, target: str) -> None:
        try:
            prompt_target = target
            if target == "当前 Git 未提交改动":
                paths = await asyncio.to_thread(self._git_changed_paths)
                if not paths:
                    raise ValueError("当前没有 Git 未提交改动")
                prompt_target = "当前 Git 未提交文件：" + "、".join(paths)
            else:
                root = self.session_manager.project_root
                candidate = Path(target)
                if not candidate.is_absolute():
                    candidate = root / candidate
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(root)
                prompt_target = str(resolved.relative_to(root)) or "."

            self._finish_local_command()
            self.run_skill("review", prompt_target)
        except asyncio.CancelledError:
            self._finish_local_command("代码审查已取消。")
        except Exception as error:
            self._finish_local_command(f"无法开始代码审查：{error}")

    def _git_changed_paths(self) -> list[str]:
        """用参数列表调用 Git，不经过 shell，也不读取配置正文。"""

        completed = subprocess.run(
            ["git", "status", "--short"],
            cwd=self.session_manager.project_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if completed.returncode != 0:
            raise ValueError("无法读取 Git 状态")
        paths = []
        for line in completed.stdout.splitlines():
            path = line[3:].strip()
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            if path:
                paths.append(path)
        return paths
