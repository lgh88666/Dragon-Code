"""读取并修复会话 JSONL。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from dragon_code.models import ChatMessage
from dragon_code.sessions.codec import SessionRecordError, record_to_message
from dragon_code.sessions.models import RestoredSession, SessionInfo


class SessionReader:
    """按完整行恢复，并跳过单行损坏。"""

    def read(self, jsonl_path: Path, session_id: str) -> RestoredSession:
        messages: list[ChatMessage] = []
        model = ""
        last_timestamp = 0
        skipped_lines = 0

        with jsonl_path.open("r", encoding="utf-8") as file:
            for raw_line in file:
                if not raw_line.strip():
                    continue
                try:
                    record = json.loads(raw_line)
                    if not isinstance(record, dict):
                        raise SessionRecordError("记录不是对象")
                    timestamp = record.get("timestamp", 0)
                    if not isinstance(timestamp, int):
                        raise SessionRecordError("时间戳类型错误")
                    if record.get("type") == "compact":
                        messages = []
                        last_timestamp = timestamp
                        continue
                    message = record_to_message(record)
                except (json.JSONDecodeError, SessionRecordError, TypeError, ValueError):
                    skipped_lines += 1
                    continue
                if not model and isinstance(record.get("model"), str):
                    model = record["model"]
                messages.append(message)
                last_timestamp = timestamp

        messages, truncated = self._truncate_orphan_tool_call(messages)
        return RestoredSession(
            session_id=session_id,
            messages=messages,
            model=model,
            last_timestamp=last_timestamp,
            skipped_lines=skipped_lines,
            orphan_call_truncated=truncated,
        )

    def info(self, jsonl_path: Path, session_id: str) -> SessionInfo:
        restored = self.read(jsonl_path, session_id)
        title = self._title(restored.messages)
        stat = jsonl_path.stat()
        timestamp = restored.last_timestamp or int(stat.st_mtime)
        return SessionInfo(
            session_id=session_id,
            title=title,
            updated_at=datetime.fromtimestamp(timestamp),
            model=restored.model or "未知模型",
            file_size=stat.st_size,
            jsonl_path=jsonl_path,
        )

    @staticmethod
    def _truncate_orphan_tool_call(
        messages: list[ChatMessage],
    ) -> tuple[list[ChatMessage], bool]:
        for index, message in enumerate(messages):
            if message.role != "assistant" or not message.tool_calls:
                continue
            if index + 1 >= len(messages):
                return messages[:index], True
            result_message = messages[index + 1]
            expected = {call.id for call in message.tool_calls}
            actual = {result.call_id for result in result_message.tool_results}
            if result_message.role != "tool" or not expected.issubset(actual):
                return messages[:index], True
        return messages, False

    @staticmethod
    def _title(messages: list[ChatMessage]) -> str:
        for message in messages:
            if message.role == "user" and message.content.strip():
                title = " ".join(message.content.split())
                return title[:50]
        return "未命名会话"
