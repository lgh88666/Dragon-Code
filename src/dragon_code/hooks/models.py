"""Hook 系统共享的简单数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from dragon_code.matching import Matcher


class HookEvent(StrEnum):
    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"
    SESSION_RESUME = "SessionResume"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    STOP = "Stop"
    PRE_USER_MESSAGE = "PreUserMessage"
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    PRE_COMPACT = "PreCompact"
    POST_COMPACT = "PostCompact"
    NOTIFICATION = "Notification"


class HookActionType(StrEnum):
    SHELL = "shell"
    PROMPT = "prompt"
    HTTP = "http"
    SUBAGENT = "subagent"


BLOCKING_EVENTS = {HookEvent.USER_PROMPT_SUBMIT, HookEvent.PRE_TOOL_USE}


@dataclass(frozen=True)
class Condition:
    field: str
    matcher: Matcher


@dataclass(frozen=True)
class ConditionGroup:
    mode: str
    conditions: tuple[Condition, ...]


@dataclass(frozen=True)
class HookAction:
    type: HookActionType
    command: str = ""
    prompt: str = ""
    url: str = ""
    method: str = "POST"
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""
    task: str = ""


@dataclass(frozen=True)
class HookDefinition:
    name: str
    event: HookEvent
    condition: ConditionGroup | None
    action: HookAction
    only_once: bool = False
    run_async: bool = False
    timeout: float = 10.0
    source: str = "project"
    source_path: Path = Path()


@dataclass(frozen=True)
class HookContext:
    event: HookEvent
    session_id: str
    cwd: Path
    mode: str
    data: dict[str, object] = field(default_factory=dict)

    def get(self, field_path: str) -> object | None:
        """用点号读取固定字段或 data 中的嵌套字段。"""

        roots: dict[str, object] = {
            **self.data,
            "event": self.event.value,
            "session_id": self.session_id,
            "cwd": str(self.cwd),
            "mode": self.mode,
        }
        current: object = roots
        for part in field_path.split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current


@dataclass(frozen=True)
class HookExecution:
    hook_name: str
    action_type: HookActionType
    status: str
    message: str = ""
    blocked: bool = False


@dataclass
class HookOutcome:
    blocked: bool = False
    reason: str = ""
    executions: list[HookExecution] = field(default_factory=list)


@dataclass(frozen=True)
class HookIssue:
    source_path: Path
    hook_name: str
    message: str


@dataclass(frozen=True)
class HookSnapshot:
    hooks: tuple[HookDefinition, ...] = ()
    issues: tuple[HookIssue, ...] = ()
