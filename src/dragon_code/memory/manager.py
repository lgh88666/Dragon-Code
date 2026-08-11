"""两级自动记忆索引、后台更新和原子写入。"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import re
import secrets
from datetime import datetime
from pathlib import Path

from dragon_code.clients.base import LLMClient
from dragon_code.memory.models import (
    VALID_ACTIONS,
    VALID_LEVELS,
    VALID_MEMORY_TYPES,
    MemoryOperation,
)
from dragon_code.memory.prompt import build_memory_request
from dragon_code.models import ChatMessage

INDEX_MAX_LINES = 200
INDEX_MAX_BYTES = 25 * 1024
MEMORY_KEYWORDS = ("记住", "记忆", "别忘", "remember", "memo")
_SAFE_FILENAME_RE = re.compile(
    r"^(user_preference|correction_feedback|project_knowledge|reference_material)_"
    r"[a-z0-9][a-z0-9-]*\.md$"
)
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)
_LOGGER = logging.getLogger(__name__)


class MemoryManager:
    """管理项目级、用户级记忆，并隔离后台失败。"""

    def __init__(self, project_root: Path, user_home: Path | None = None):
        self.project_root = project_root.resolve()
        self.user_home = (user_home or Path.home()).resolve()
        self.project_memory_dir = self.project_root / ".dragon-code" / "memory"
        self.user_memory_dir = self.user_home / ".dragon-code" / "memory"
        self._current_index = ""
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()

    def load_indexes(self) -> str:
        """加载两级索引快照；任何单级失败都按空索引降级。"""

        project = self._read_index(self.project_memory_dir / "MEMORY.md")
        user = self._read_index(self.user_memory_dir / "MEMORY.md")
        sections: list[str] = []
        if project:
            sections.append("## 项目记忆\n" + project)
        if user:
            sections.append("## 用户记忆\n" + user)
        self._current_index = _truncate_utf8(
            "\n\n".join(sections),
            INDEX_MAX_BYTES,
            marker="\n(index truncated)",
        )
        return self._current_index

    def current_index(self) -> str:
        """返回不可变字符串快照。"""

        return self._current_index

    def should_update(self, completed_turns: int, user_text: str) -> bool:
        """每五个自然完成回合或出现明确记忆关键词时触发。"""

        if completed_turns > 0 and completed_turns % 5 == 0:
            return True
        lowered = user_text.lower()
        return any(keyword in lowered for keyword in MEMORY_KEYWORDS)

    def schedule_update(
        self,
        client: LLMClient,
        turn_messages: list[ChatMessage],
        completed_turns: int,
        user_text: str,
    ) -> None:
        """需要时启动后台任务，不等待模型或磁盘。"""

        if not self.should_update(completed_turns, user_text):
            return
        snapshot = copy.deepcopy(turn_messages)
        task = asyncio.create_task(self._update_memory(client, snapshot))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def close(self) -> None:
        """取消并等待后台任务，避免退出后泄漏。"""

        tasks = list(self._tasks)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    async def _update_memory(
        self,
        client: LLMClient,
        turn_messages: list[ChatMessage],
    ) -> None:
        try:
            request = build_memory_request(turn_messages, self.current_index())
            text = await self._collect_response(client, request)
            operations = self._parse_operations(text)
            if not operations:
                return
            async with self._lock:
                await asyncio.to_thread(self._apply_operations, operations)
                self.load_indexes()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # 自动记忆是附加能力，错误只进内部日志，不能污染主对话。
            _LOGGER.warning("自动记忆更新失败：%s", type(error).__name__)

    async def _collect_response(self, client: LLMClient, request) -> str:
        chunks: list[str] = []
        completed = ""
        async for event in client.stream(request):
            if event.type == "text_delta" and event.text:
                chunks.append(event.text)
            elif event.type == "completed" and event.message is not None:
                if event.message.tool_calls:
                    raise ValueError("记忆模型不允许调用工具")
                completed = event.message.content
        text = completed or "".join(chunks)
        if not text.strip():
            raise ValueError("记忆模型没有返回内容")
        return text

    def _parse_operations(self, text: str) -> list[MemoryOperation]:
        """解析并过滤 LLM 返回的不可信操作。"""

        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        data = json.loads(cleaned)
        if not isinstance(data, list):
            raise ValueError("记忆操作必须是数组")

        operations: list[MemoryOperation] = []
        for item in data:
            operation = self._validate_operation(item)
            if operation is not None:
                operations.append(operation)
        return operations

    def _validate_operation(self, item: object) -> MemoryOperation | None:
        if not isinstance(item, dict):
            return None
        action = item.get("action")
        level = item.get("level")
        if action not in VALID_ACTIONS or level not in VALID_LEVELS:
            return None
        if not all(isinstance(value, str) for value in item.values()):
            return None

        if action == "create":
            memory_type = item.get("memory_type", "")
            title = item.get("title", "").strip()
            content = item.get("content", "").strip()
            slug = _safe_slug(item.get("slug", ""))
            if memory_type not in VALID_MEMORY_TYPES or not title or not content or not slug:
                return None
            expected_level = (
                "user" if memory_type in {"user_preference", "correction_feedback"} else "project"
            )
            return MemoryOperation(
                action="create",
                level=expected_level,
                memory_type=memory_type,
                title=title,
                slug=slug,
                content=content,
            )

        filename = item.get("filename", "")
        if not _is_safe_filename(filename):
            return None
        if action == "delete":
            return MemoryOperation(action="delete", level=level, filename=filename)

        title = item.get("title", "").strip()
        content = item.get("content", "").strip()
        if not title or not content:
            return None
        return MemoryOperation(
            action="update",
            level=level,
            filename=filename,
            title=title,
            content=content,
        )

    def _apply_operations(self, operations: list[MemoryOperation]) -> None:
        touched: set[Path] = set()
        for operation in operations:
            directory = self._directory_for_level(operation.level)
            directory.mkdir(parents=True, exist_ok=True)
            touched.add(directory)
            if operation.action == "create":
                filename = f"{operation.memory_type}_{operation.slug}.md"
                path = directory / filename
                if path.exists():
                    continue
                now = datetime.now().isoformat(timespec="seconds")
                text = _render_note(
                    operation.memory_type,
                    operation.title,
                    now,
                    now,
                    operation.content,
                )
                _atomic_write(path, text)
            elif operation.action == "update":
                path = directory / operation.filename
                existing = _read_note(path)
                if existing is None:
                    continue
                memory_type, _old_title, created, _updated, _body = existing
                now = datetime.now().isoformat(timespec="seconds")
                text = _render_note(
                    memory_type,
                    operation.title,
                    created,
                    now,
                    operation.content,
                )
                _atomic_write(path, text)
            else:
                path = directory / operation.filename
                if path.is_file():
                    path.unlink()

        for directory in touched:
            self._rebuild_index(directory)

    def _rebuild_index(self, directory: Path) -> None:
        lines: list[str] = []
        for path in sorted(directory.glob("*.md")):
            if path.name == "MEMORY.md" or not _is_safe_filename(path.name):
                continue
            note = _read_note(path)
            if note is None:
                continue
            memory_type, title, _created, _updated, body = note
            summary = " ".join(body.split())[:160]
            lines.append(f"- [{title}]({path.name}) — {memory_type}: {summary}")
        index = _limit_index_lines(lines)
        _atomic_write(directory / "MEMORY.md", index)

    def _read_index(self, path: Path) -> str:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""
        return _limit_index_lines(text.splitlines())

    def _directory_for_level(self, level: str) -> Path:
        return self.project_memory_dir if level == "project" else self.user_memory_dir


def _safe_slug(value: str) -> str:
    lowered = value.strip().lower().replace("_", "-")
    slug = re.sub(r"[^a-z0-9-]+", "-", lowered).strip("-")
    return slug[:60]


def _is_safe_filename(value: str) -> bool:
    if not isinstance(value, str) or Path(value).name != value:
        return False
    return _SAFE_FILENAME_RE.fullmatch(value) is not None


def _render_note(
    memory_type: str,
    title: str,
    created: str,
    updated: str,
    body: str,
) -> str:
    safe_title = title.replace("\n", " ").strip()
    return (
        "---\n"
        f"type: {memory_type}\n"
        f"title: {safe_title}\n"
        f"created: {created}\n"
        f"updated: {updated}\n"
        "---\n"
        f"{body.strip()}\n"
    )


def _read_note(path: Path) -> tuple[str, str, str, str, str] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return None
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip()
    required = [fields.get(name, "") for name in ("type", "title", "created", "updated")]
    if not all(required) or required[0] not in VALID_MEMORY_TYPES:
        return None
    return required[0], required[1], required[2], required[3], match.group(2).strip()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{secrets.token_hex(4)}.tmp"
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _limit_index_lines(lines: list[str]) -> str:
    text = "\n".join(lines[:INDEX_MAX_LINES]).strip()
    return _truncate_utf8(text, INDEX_MAX_BYTES, marker="\n(index truncated)")


def _truncate_utf8(text: str, max_bytes: int, marker: str) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    marker_bytes = marker.encode("utf-8")
    available = max(0, max_bytes - len(marker_bytes))
    prefix = encoded[:available].decode("utf-8", errors="ignore")
    return prefix + marker
