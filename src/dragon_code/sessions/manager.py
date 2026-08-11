"""创建、列出、恢复和清理会话。"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from dragon_code.context.state import SessionPaths, is_new_session_id, make_session_id
from dragon_code.models import ChatMessage
from dragon_code.session import Conversation
from dragon_code.sessions.models import SessionInfo
from dragon_code.sessions.reader import SessionReader
from dragon_code.sessions.writer import SessionWriter

_SIX_HOURS = 6 * 60 * 60


@dataclass
class ActiveSession:
    """TUI 当前使用的一套会话对象。"""

    session_id: str
    conversation: Conversation
    writer: SessionWriter
    restored_count: int = 0
    restore_notices: list[str] = field(default_factory=list)


class SessionManager:
    """会话目录入口；不会替 TUI 自动关闭旧会话。"""

    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.sessions_root = self.project_root / ".dragon-code" / "sessions"
        self.reader = SessionReader()
        self._writers: list[SessionWriter] = []

    def open_new(self, model: str) -> ActiveSession:
        while True:
            session_id = make_session_id()
            paths = SessionPaths.create(self.project_root, session_id)
            if not paths.session_dir.exists():
                break
        return self._build_active(paths, model, [])

    def list_sessions(self) -> list[SessionInfo]:
        if not self.sessions_root.exists():
            return []
        sessions: list[SessionInfo] = []
        for directory in self.sessions_root.iterdir():
            if not directory.is_dir() or not is_new_session_id(directory.name):
                continue
            jsonl_path = directory / "conversation.jsonl"
            if not jsonl_path.is_file():
                continue
            try:
                sessions.append(self.reader.info(jsonl_path, directory.name))
            except OSError:
                continue
        sessions.sort(key=lambda item: item.updated_at, reverse=True)
        return sessions

    def restore(self, session_id: str, model: str) -> ActiveSession:
        if not is_new_session_id(session_id):
            raise ValueError("只能恢复新格式会话")
        paths = SessionPaths.create(self.project_root, session_id)
        jsonl_path = paths.session_dir / "conversation.jsonl"
        restored = self.reader.read(jsonl_path, session_id)
        messages = list(restored.messages)
        notices: list[str] = []
        if restored.skipped_lines:
            notices.append(f"已跳过 {restored.skipped_lines} 行损坏记录")
        if restored.orphan_call_truncated:
            notices.append("已截断缺少工具结果的末尾记录")
        if restored.last_timestamp and int(time.time()) - restored.last_timestamp > _SIX_HOURS:
            reminder = (
                "<system-reminder>\n"
                "距离上次对话已超过 6 小时，请先结合现有上下文确认当前状态。\n"
                "</system-reminder>"
            )
            if messages and messages[-1].role == "user":
                messages[-1].content = f"{messages[-1].content}\n\n{reminder}"
            else:
                messages.append(ChatMessage("user", reminder))
            notices.append("距离上次对话已超过 6 小时")
        active = self._build_active(paths, model, messages)
        active.restored_count = len(restored.messages)
        active.restore_notices = notices
        return active

    def cleanup_expired(self, retention_days: int = 45) -> list[str]:
        if not self.sessions_root.exists():
            return []
        cutoff = time.time() - retention_days * 24 * 60 * 60
        deleted: list[str] = []
        root = self.sessions_root.resolve()
        for directory in list(self.sessions_root.iterdir()):
            if not directory.is_dir() or not is_new_session_id(directory.name):
                continue
            try:
                resolved = directory.resolve(strict=True)
                resolved.relative_to(root)
                jsonl_path = resolved / "conversation.jsonl"
                updated_at = resolved.stat().st_mtime
                if jsonl_path.is_file():
                    restored = self.reader.read(jsonl_path, directory.name)
                    updated_at = restored.last_timestamp or jsonl_path.stat().st_mtime
                if updated_at >= cutoff:
                    continue
                shutil.rmtree(resolved)
            except (OSError, RuntimeError, ValueError):
                continue
            deleted.append(directory.name)
        return deleted

    def close(self) -> None:
        for writer in self._writers:
            writer.close()
        self._writers.clear()

    def _build_active(
        self,
        paths: SessionPaths,
        model: str,
        initial_messages: list[ChatMessage],
    ) -> ActiveSession:
        writer = SessionWriter(paths.session_dir / "conversation.jsonl", model)
        self._writers.append(writer)
        conversation = Conversation(
            initial_messages=initial_messages,
            on_append=writer.append,
            on_replace=writer.replace,
        )
        return ActiveSession(paths.session_id, conversation, writer)
