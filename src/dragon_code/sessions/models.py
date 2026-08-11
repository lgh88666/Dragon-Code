"""会话列表和恢复使用的数据结构。"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dragon_code.models import ChatMessage


@dataclass
class SessionInfo:
    """会话选择列表中的一项。"""

    session_id: str
    title: str
    updated_at: datetime
    model: str
    file_size: int
    jsonl_path: Path


@dataclass
class RestoredSession:
    """从 JSONL 读取并修复后的会话。"""

    session_id: str
    messages: list[ChatMessage]
    model: str
    last_timestamp: int
    skipped_lines: int
    orphan_call_truncated: bool
