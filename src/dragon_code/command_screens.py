"""Slash Command 的 Textual 交互界面。"""

from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static

from dragon_code.command.command import Command
from dragon_code.memory import MemoryInfo
from dragon_code.permissions import PermissionMode
from dragon_code.sessions import SessionInfo


class CommandHelpScreen(ModalScreen[None]):
    """从注册中心数据生成的命令帮助。"""

    BINDINGS = [Binding("escape", "close", show=False, priority=True)]

    def __init__(self, commands: list[Command]):
        super().__init__()
        self.commands = commands

    def compose(self) -> ComposeResult:
        labels = [f"/{item.name}  {item.description}" for item in self.commands]
        with Vertical(id="command-help-dialog"):
            yield Static("Dragon Code 命令", classes="command-screen-title")
            with Horizontal(id="command-help-body"):
                yield OptionList(*labels, id="command-help-options")
                yield Static("", id="command-help-detail")
            yield Static("↑↓ 选择 · Enter 查看 · Esc 关闭", classes="command-screen-hint")

    def on_mount(self) -> None:
        options = self.query_one("#command-help-options", OptionList)
        options.highlighted = 0
        options.focus()
        self._show_detail(0)

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self._show_detail(event.option_index)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._show_detail(event.option_index)

    def submit_highlighted(self) -> None:
        options = self.query_one("#command-help-options", OptionList)
        self._show_detail(options.highlighted or 0)

    def action_close(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        """与其他命令弹窗统一，供 App 的全局 Esc 入口调用。"""

        self.dismiss(None)

    def _show_detail(self, index: int) -> None:
        if not self.commands or index >= len(self.commands):
            return
        command = self.commands[index]
        aliases = "、".join(f"/{alias}" for alias in command.aliases) or "无"
        detail = (
            f"/{command.name}\n\n"
            f"{command.description}\n\n"
            f"类型：{command.kind.value}\n"
            f"用法：{command.usage}\n"
            f"别名：{aliases}"
        )
        self.query_one("#command-help-detail", Static).update(detail)


@dataclass
class SessionScreenResult:
    action: str
    session_id: str


class SessionCommandScreen(ModalScreen[SessionScreenResult | None]):
    """搜索、恢复或删除历史会话。"""

    BINDINGS = [
        Binding("delete", "delete_selected", show=False, priority=True),
        Binding("escape", "cancel", show=False, priority=True),
    ]

    def __init__(
        self,
        sessions: list[SessionInfo],
        active_session_id: str,
        *,
        resume_only: bool,
    ):
        super().__init__()
        self.sessions = sessions
        self.filtered = list(sessions)
        self.active_session_id = active_session_id
        self.resume_only = resume_only

    def compose(self) -> ComposeResult:
        title = "恢复历史会话" if self.resume_only else "管理历史会话"
        hint = "Enter 恢复 · Esc 关闭"
        if not self.resume_only:
            hint = "Enter 恢复 · Delete 删除 · Esc 关闭"
        with Vertical(id="session-command-dialog"):
            yield Static(title, classes="command-screen-title")
            yield Input(placeholder="按标题或会话 ID 搜索…", id="session-command-search")
            yield OptionList(*self._labels(), id="session-command-options")
            yield Static(hint, classes="command-screen-hint")

    def on_mount(self) -> None:
        self.query_one("#session-command-search", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        keyword = event.value.strip().lower()
        self.filtered = [
            item
            for item in self.sessions
            if not keyword or keyword in item.title.lower() or keyword in item.session_id.lower()
        ]
        options = self.query_one("#session-command-options", OptionList)
        options.clear_options()
        options.add_options(self._labels() or ["没有匹配的会话"])

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._dismiss_action("resume", event.option_index)

    def submit_highlighted(self) -> None:
        index = self.query_one("#session-command-options", OptionList).highlighted or 0
        self._dismiss_action("resume", index)

    def action_delete_selected(self) -> None:
        if self.resume_only:
            return
        index = self.query_one("#session-command-options", OptionList).highlighted or 0
        self._dismiss_action("delete", index)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _dismiss_action(self, action: str, index: int) -> None:
        if index < len(self.filtered):
            self.dismiss(SessionScreenResult(action, self.filtered[index].session_id))

    def _labels(self) -> list[str]:
        labels = []
        for item in self.filtered:
            current = "  ·  当前" if item.session_id == self.active_session_id else ""
            labels.append(
                f"{item.title}  ·  {item.updated_at:%m-%d %H:%M}  ·  {item.model}{current}"
            )
        return labels


@dataclass
class MemoryScreenResult:
    action: str
    memory: MemoryInfo


class MemoryCommandScreen(ModalScreen[MemoryScreenResult | None]):
    """展示两级记忆，并允许查看或删除。"""

    BINDINGS = [
        Binding("delete", "delete_selected", show=False, priority=True),
        Binding("escape", "cancel", show=False, priority=True),
    ]

    def __init__(self, memories: list[MemoryInfo]):
        super().__init__()
        self.memories = memories

    def compose(self) -> ComposeResult:
        labels = [f"[{item.level}] {item.title}  ·  {item.filename}" for item in self.memories]
        with Vertical(id="memory-command-dialog"):
            yield Static("长期记忆", classes="command-screen-title")
            with Horizontal(id="memory-command-body"):
                yield OptionList(*(labels or ["当前没有记忆"]), id="memory-command-options")
                yield Static("", id="memory-command-detail")
            yield Static("↑↓ 查看 · Delete 删除 · Esc 关闭", classes="command-screen-hint")

    def on_mount(self) -> None:
        options = self.query_one("#memory-command-options", OptionList)
        options.highlighted = 0
        options.focus()
        self._show_detail(0)

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self._show_detail(event.option_index)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_index < len(self.memories):
            self.dismiss(MemoryScreenResult("view", self.memories[event.option_index]))

    def submit_highlighted(self) -> None:
        index = self.query_one("#memory-command-options", OptionList).highlighted or 0
        if index < len(self.memories):
            self.dismiss(MemoryScreenResult("view", self.memories[index]))

    def action_delete_selected(self) -> None:
        index = self.query_one("#memory-command-options", OptionList).highlighted or 0
        if index < len(self.memories):
            self.dismiss(MemoryScreenResult("delete", self.memories[index]))

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _show_detail(self, index: int) -> None:
        if index >= len(self.memories):
            return
        item = self.memories[index]
        detail = (
            f"{item.title}\n\n层级：{item.level}\n类型：{item.memory_type}\n"
            f"文件：{item.filename}\n\n{item.content}"
        )
        self.query_one("#memory-command-detail", Static).update(detail)


class PermissionModeScreen(ModalScreen[PermissionMode | None]):
    """选择本次运行使用的权限模式。"""

    BINDINGS = [Binding("escape", "cancel", show=False, priority=True)]
    MODES = [
        PermissionMode.DEFAULT,
        PermissionMode.ACCEPT_EDITS,
        PermissionMode.BYPASS_PERMISSIONS,
    ]

    def __init__(self, current: PermissionMode):
        super().__init__()
        self.current = current

    def compose(self) -> ComposeResult:
        descriptions = {
            PermissionMode.DEFAULT: "写文件和命令需要确认",
            PermissionMode.ACCEPT_EDITS: "文件修改自动允许",
            PermissionMode.BYPASS_PERMISSIONS: "日常操作自动允许，硬防线仍生效",
        }
        labels = []
        for mode in self.MODES:
            marker = "（当前）" if mode is self.current else ""
            labels.append(f"{mode.value} {marker}  ·  {descriptions[mode]}")
        with Vertical(id="permission-mode-dialog"):
            yield Static("运行时权限模式", classes="command-screen-title")
            yield OptionList(*labels, id="permission-mode-options")
            yield Static("Enter 选择 · Esc 取消（不会修改 YAML）", classes="command-screen-hint")

    def on_mount(self) -> None:
        options = self.query_one("#permission-mode-options", OptionList)
        options.highlighted = self.MODES.index(self.current) if self.current in self.MODES else 0
        options.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(self.MODES[event.option_index])

    def submit_highlighted(self) -> None:
        index = self.query_one("#permission-mode-options", OptionList).highlighted or 0
        self.dismiss(self.MODES[index])

    def action_cancel(self) -> None:
        self.dismiss(None)


class ReviewTargetScreen(ModalScreen[str | None]):
    """选择审查当前改动，或输入一个项目内路径。"""

    BINDINGS = [Binding("escape", "cancel", show=False, priority=True)]

    def compose(self) -> ComposeResult:
        with Vertical(id="review-target-dialog"):
            yield Static("选择代码审查目标", classes="command-screen-title")
            yield OptionList("当前 Git 未提交改动", "指定文件或目录", id="review-target-options")
            yield Input(placeholder="选择第二项后输入项目内路径…", id="review-target-input")
            yield Static("Enter 确认 · Esc 取消", classes="command-screen-hint")

    def on_mount(self) -> None:
        options = self.query_one("#review-target-options", OptionList)
        options.highlighted = 0
        options.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_index == 0:
            self.dismiss("当前 Git 未提交改动")
        else:
            self.query_one("#review-target-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if value:
            self.dismiss(value)

    def submit_highlighted(self) -> None:
        focused = self.focused
        if isinstance(focused, Input):
            value = focused.value.strip()
            if value:
                self.dismiss(value)
            return
        options = self.query_one("#review-target-options", OptionList)
        if (options.highlighted or 0) == 0:
            self.dismiss("当前 Git 未提交改动")
        else:
            self.query_one("#review-target-input", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmCommandScreen(ModalScreen[bool]):
    """会话和记忆删除共用的明确确认框。"""

    BINDINGS = [Binding("escape", "cancel", show=False, priority=True)]

    def __init__(self, title: str, target: str):
        super().__init__()
        self.title = title
        self.target = target

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-command-dialog"):
            yield Static(self.title, classes="command-screen-title")
            yield Static(self.target, id="confirm-command-target")
            yield OptionList("取消", "确认永久删除", id="confirm-command-options")

    def on_mount(self) -> None:
        options = self.query_one("#confirm-command-options", OptionList)
        options.highlighted = 0
        options.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option_index == 1)

    def submit_highlighted(self) -> None:
        index = self.query_one("#confirm-command-options", OptionList).highlighted or 0
        self.dismiss(index == 1)

    def action_cancel(self) -> None:
        self.dismiss(False)
