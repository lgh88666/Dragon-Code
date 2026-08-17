"""SubAgent 模块共用的简单数据类型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum, StrEnum
from pathlib import Path

from dragon_code.models import TokenUsage, ToolCall, ToolResult
from dragon_code.permissions import PermissionMode


class AgentDefinitionSource(IntEnum):
    """Agent 定义来源；数值越大，覆盖优先级越高。"""

    PLUGIN = 0
    BUILTIN = 1
    USER = 2
    PROJECT = 3


class SubAgentKind(StrEnum):
    DEFINED = "defined"
    FORK = "fork"
    SKILL_FORK = "skill_fork"


class QuerySource(StrEnum):
    """标记一次 Agent Loop 从哪里发起，用于阻止嵌套委派。"""

    MAIN = "main"
    DEFINED_SUBAGENT = "defined_subagent"
    FORK_SUBAGENT = "fork_subagent"
    SKILL_FORK = "skill_fork"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class AgentDefinition:
    name: str
    description: str
    system_prompt: str
    allowed_tools: tuple[str, ...]
    disallowed_tools: tuple[str, ...]
    model: str
    max_iterations: int
    permission_mode: PermissionMode
    background: bool
    source: AgentDefinitionSource
    source_path: Path


@dataclass(frozen=True)
class AgentDefinitionIssue:
    source_path: Path
    code: str
    message: str


@dataclass(frozen=True)
class SubAgentLaunchRequest:
    prompt: str
    description: str
    role_name: str = ""
    model_override: str = ""
    run_in_background: bool = False
    task_name: str = ""
    kind: SubAgentKind = SubAgentKind.DEFINED
    skill_name: str = ""
    skill_arguments: str = ""
    skill_context: str = "full"
    skill_allowed_tools: tuple[str, ...] = ()
    skill_system_prompt: str = ""


@dataclass(frozen=True)
class SubAgentResult:
    text: str
    usage: TokenUsage
    tool_count: int
    stop_reason: str


@dataclass(frozen=True)
class TaskSnapshot:
    id: str
    name: str
    description: str
    kind: SubAgentKind
    status: TaskStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    result: str
    error: str
    usage: TokenUsage
    tool_count: int
    last_activity: datetime
    attached: bool
    queued_position: int | None = None


@dataclass(frozen=True)
class SubAgentEvent:
    type: str
    task_id: str
    task_name: str
    agent_name: str
    attached: bool
    text: str = ""
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None
    usage: TokenUsage | None = None
    status: TaskStatus | None = None
    iteration: int = 0
    max_iterations: int = 0
    running_count: int = 0
    queued_count: int = 0


@dataclass(frozen=True)
class SubAgentLaunchOutcome:
    task_id: str
    status: str
    text: str = ""
    background: bool = False


@dataclass(frozen=True)
class TaskWaitOutcome:
    task: TaskSnapshot
    reason: str


@dataclass
class SubAgentSession:
    """可被 SendMessage 继续使用的隔离会话。"""

    key: str
    name: str
    kind: SubAgentKind
    agent_name: str
    agent: object
    conversation: object
    hook_engine: object
    definition: AgentDefinition | None = None
    metadata: dict[str, object] = field(default_factory=dict)
