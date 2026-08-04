"""权限系统共用的数据类型。"""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from dragon_code.models import ToolCall


class PermissionMode(StrEnum):
    """Dragon Code 支持的四种权限模式。"""

    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    PLAN = "plan"
    BYPASS_PERMISSIONS = "bypassPermissions"


class PermissionDecision(StrEnum):
    """一次权限判断的最终结论。"""

    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class ApprovalChoice(StrEnum):
    """用户在权限确认框中的三个选择。"""

    ALLOW_ONCE = "allow_once"
    ALLOW_ALWAYS = "allow_always"
    DENY_ONCE = "deny_once"


@dataclass(frozen=True)
class PermissionResult:
    """权限引擎返回给 Agent 的判断结果。"""

    decision: PermissionDecision
    source: str
    reason: str
    matched_rule: str = ""


@dataclass(frozen=True)
class PermissionRule:
    """解析后的单条权限规则。"""

    tool_name: str
    pattern: str | None
    decision: PermissionDecision
    raw: str


@dataclass
class RuleLayer:
    """用户级、项目级或本地级的一层权限设置。"""

    name: str
    path: Path
    allow: list[PermissionRule] = field(default_factory=list)
    deny: list[PermissionRule] = field(default_factory=list)
    default_mode: PermissionMode | None = None


@dataclass(frozen=True)
class PermissionRequest:
    """Agent 发给 TUI 的一次审批请求。"""

    call: ToolCall
    reason: str
    summary: str
    exact_rule: str
