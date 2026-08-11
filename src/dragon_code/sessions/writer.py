"""追加写会话 JSONL。"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import TextIO

from dragon_code.models import ChatMessage
from dragon_code.sessions.codec import compact_record, message_to_record


class SessionWriter:
    """使用单锁写入完整 JSON 行，并在每行后刷盘。"""

    def __init__(self, jsonl_path: Path, model: str):
        self.jsonl_path = jsonl_path
        self.model = model
        self._lock = threading.Lock()
        self._closed = False
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self._model_written = self.jsonl_path.exists() and self.jsonl_path.stat().st_size > 0
        self._file: TextIO = self.jsonl_path.open("a", encoding="utf-8", newline="\n")

    def append(self, message: ChatMessage) -> None:
        """追加一条完整逻辑消息。"""

        with self._lock:
            self._ensure_open()
            model = None if self._model_written else self.model
            self._write_record(message_to_record(message, int(time.time()), model))
            self._model_written = True

    def replace(self, messages: list[ChatMessage]) -> None:
        """追加压缩边界和替换后的完整历史。"""

        with self._lock:
            self._ensure_open()
            now = int(time.time())
            self._write_record(compact_record(now))
            for message in messages:
                model = None if self._model_written else self.model
                self._write_record(message_to_record(message, now, model))
                self._model_written = True

    def close(self) -> None:
        """幂等关闭文件。"""

        with self._lock:
            if self._closed:
                return
            self._file.close()
            self._closed = True

    def _write_record(self, record: dict) -> None:
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        self._file.write(line + "\n")
        self._file.flush()
        os.fsync(self._file.fileno())

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("会话存档已经关闭")
