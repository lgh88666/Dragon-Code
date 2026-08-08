"""上下文管理的简单状态对象。"""

from __future__ import annotations

import hashlib
import re
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from dragon_code.context.constants import COMPACT_FAILURE_LIMIT

if TYPE_CHECKING:
    from dragon_code.models import ChatMessage

_SAFE_PREFIX_RE = re.compile(r"[^A-Za-z0-9_-]+")


def make_session_id() -> str:
    """生成适合 Windows 路径且进程内足够唯一的会话 ID。"""

    return f"{int(time.time())}-{secrets.token_hex(4)}"


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
        resolved_session_id = session_id or make_session_id()
        if not re.fullmatch(r"\d+-[0-9a-f]{8}", resolved_session_id):
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
