"""命令层可使用的界面控制接口。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from dragon_code.command.command import Command
    from dragon_code.skills import SkillDefinition, SkillLoadIssue


@dataclass
class CommandStatus:
    """执行 /status 时读取的一次性状态快照。"""

    version: str
    cwd: str
    provider: str
    model: str
    permission_mode: str
    session_id: str
    input_tokens: int | None
    output_tokens: int | None
    cache_write_tokens: int
    cache_read_tokens: int
    estimated_context_tokens: int
    builtin_tool_count: int
    mcp_tool_count: int
    user_memory_count: int
    project_memory_count: int


class CommandUI(Protocol):
    """命令只依赖这些能力，不直接依赖 Textual。"""

    def is_idle(self) -> bool: ...

    def show_message(self, text: str, *, error: bool = False) -> None: ...

    def open_help(self, commands: list[Command]) -> None: ...

    def get_status(self) -> CommandStatus: ...

    def quit(self) -> None: ...

    def force_compact(self) -> None: ...

    def clear_session(self) -> None: ...

    def enter_plan_mode(self) -> None: ...

    def execute_plan(self) -> None: ...

    def open_sessions(self, *, resume_only: bool = False) -> None: ...

    def open_memories(self) -> None: ...

    def open_permissions(self) -> None: ...

    def open_review(self) -> None: ...

    def open_skills(self) -> None: ...

    def run_skill(self, name: str, arguments: str = "") -> None: ...

    def skill_items(self) -> tuple[list[SkillDefinition], list[SkillLoadIssue]]: ...

    def reload_skills(self) -> tuple[list[SkillDefinition], list[SkillLoadIssue]]: ...
