"""上下文管理的简单状态对象。"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from dragon_code.context.constants import COMPACT_FAILURE_LIMIT

if TYPE_CHECKING:
    from dragon_code.models import ChatMessage

_SAFE_PREFIX_RE = re.compile(r"[^A-Za-z0-9_-]+")
_NEW_SESSION_ID_RE = re.compile(r"\d{8}-\d{6}-[0-9a-f]{4}")
_LEGACY_SESSION_ID_RE = re.compile(r"\d+-[0-9a-f]{8}")


def make_session_id() -> str:
    """生成适合列表展示、Windows 路径和同秒并发的会话 ID。"""

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{secrets.token_hex(2)}"


def is_new_session_id(value: str) -> bool:
    """判断是否为 ch09 新会话 ID。"""

    return _NEW_SESSION_ID_RE.fullmatch(value) is not None


def is_safe_session_id(value: str) -> bool:
    """兼容 ch08 旧 ID，但拒绝任何路径字符。"""

    return is_new_session_id(value) or _LEGACY_SESSION_ID_RE.fullmatch(value) is not None


def safe_result_filename(call_id: str) -> str:
    """把不可信调用 ID 映射为稳定、无目录穿越风险的文件名。"""

    prefix = _SAFE_PREFIX_RE.sub("-", call_id).strip("-_")[:32] or "call"
    digest = hashlib.sha256(call_id.encode("utf-8")).hexdigest()[:12]
    return f"tool-{prefix}-{digest}.txt"


@dataclass(frozen=True)
class SessionPaths:
    """当前进程会话的持久结果目录。"""

    working_dir: Path
    session_id: str
    session_dir: Path
    tool_results_dir: Path

    @classmethod
    def create(cls, working_dir: Path, session_id: str | None = None) -> SessionPaths:
        root = working_dir.resolve()
        resolved_session_id = make_session_id() if session_id is None else session_id
        if not is_safe_session_id(resolved_session_id):
            raise ValueError("session_id 格式不安全")
        session_dir = root / ".dragon-code" / "sessions" / resolved_session_id
        return cls(
            working_dir=root,
            session_id=resolved_session_id,
            session_dir=session_dir,
            tool_results_dir=session_dir / "tool-results",
        )

    def result_path(self, call_id: str) -> Path:
        return self.tool_results_dir / safe_result_filename(call_id)


@dataclass(frozen=True)
class ReplacementDecision:
    """一次工具结果已经冻结的保留或替换决定。"""

    replaced: bool
    preview: str = ""
    file_path: Path | None = None
    original_bytes: int = 0


@dataclass
class ReplacementLedger:
    """确保同一调用 ID 在会话内只产生一次最终决定。"""

    _decisions: dict[str, ReplacementDecision] = field(default_factory=dict)

    def get(self, call_id: str) -> ReplacementDecision | None:
        return self._decisions.get(call_id)

    def freeze(self, call_id: str, decision: ReplacementDecision) -> ReplacementDecision:
        existing = self._decisions.get(call_id)
        if existing is not None:
            return existing
        self._decisions[call_id] = decision
        return decision


@dataclass
class UsageAnchor:
    """最近一次主请求 usage 覆盖到的字符位置。"""

    total_tokens: int = 0
    covered_chars: int = 0
    valid: bool = False

    def update(self, total_tokens: int, covered_chars: int) -> None:
        if total_tokens < 0 or covered_chars < 0:
            raise ValueError("usage 锚点不能是负数")
        self.total_tokens = total_tokens
        self.covered_chars = covered_chars
        self.valid = True

    def invalidate(self) -> None:
        self.valid = False


@dataclass
class CompactCircuitBreaker:
    """只统计自动摘要连续失败的会话级熔断器。"""

    consecutive_failures: int = 0
    failure_limit: int = COMPACT_FAILURE_LIMIT

    @property
    def tripped(self) -> bool:
        return self.consecutive_failures >= self.failure_limit

    def record_failure(self) -> None:
        self.consecutive_failures += 1

    def record_success(self) -> None:
        self.consecutive_failures = 0


@dataclass(frozen=True)
class CompactStats:
    """一次压缩尝试的安全统计。"""

    reason: str
    before_tokens: int
    after_tokens: int | None = None
    offloaded_results: int = 0
    error: str = ""


@dataclass
class CompactOutcome:
    """一次压缩尝试及其候选新历史。"""

    success: bool
    history: list[ChatMessage]
    stats: CompactStats


@dataclass
class PrepareResult:
    """普通主请求发送前的上下文准备结果。"""

    committed_history: list[ChatMessage]
    request_messages: list[ChatMessage]
    compact: CompactOutcome | None = None
    circuit_tripped: bool = False
