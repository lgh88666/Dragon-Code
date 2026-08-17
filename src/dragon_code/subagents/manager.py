"""SubAgent 前台、后台和排队任务管理。"""

from __future__ import annotations

import asyncio
import secrets
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime

from dragon_code.models import AgentEvent, TokenUsage
from dragon_code.subagents.models import (
    SubAgentEvent,
    SubAgentKind,
    SubAgentResult,
    SubAgentSession,
    TaskSnapshot,
    TaskStatus,
    TaskWaitOutcome,
)

MAX_STORED_RESULT = 100_000
MAX_TASK_RESULT = 50_000
MAX_NOTIFICATION = 2_000

TaskRunner = Callable[[str], Awaitable[SubAgentResult]]


class TaskManagerError(ValueError):
    """任务请求不合法或当前状态不允许该操作。"""


@dataclass
class _TaskRecord:
    id: str
    name: str
    description: str
    kind: SubAgentKind
    session: SubAgentSession
    runner: TaskRunner
    status: TaskStatus
    created_at: datetime
    last_activity: datetime
    attached: bool
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: str = ""
    error: str = ""
    usage: TokenUsage = field(default_factory=lambda: TokenUsage(0, 0))
    tool_count: int = 0
    detach_reason: str = ""
    task: asyncio.Task[None] | None = None
    started_event: asyncio.Event = field(default_factory=asyncio.Event)
    detached_event: asyncio.Event = field(default_factory=asyncio.Event)
    done_event: asyncio.Event = field(default_factory=asyncio.Event)


def _now() -> datetime:
    return datetime.now().astimezone()


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 14] + "\n[truncated]"


class BackgroundTaskManager:
    """在一个 asyncio 事件循环内管理最多三个并发子 Agent。"""

    def __init__(self, *, max_concurrent: int = 3, foreground_timeout: float = 120.0):
        self.max_concurrent = max_concurrent
        self.foreground_timeout = foreground_timeout
        self._records: dict[str, _TaskRecord] = {}
        self._queue: deque[str] = deque()
        self._running: set[str] = set()
        self._sessions_by_name: dict[str, SubAgentSession] = {}
        self._events: list[SubAgentEvent] = []
        self._reminders: list[str] = []
        self._sensitive_values: set[str] = set()
        self._lock = asyncio.Lock()
        self._closed = False

    def add_sensitive_value(self, value: str) -> None:
        """登记不能出现在任务状态、结果或通知中的明文。"""

        if len(value) >= 4:
            self._sensitive_values.add(value)

    def _safe_text(self, value: str) -> str:
        safe = value
        for sensitive in self._sensitive_values:
            safe = safe.replace(sensitive, "[REDACTED]")
        return safe

    async def submit(
        self,
        session: SubAgentSession,
        prompt: str,
        runner: TaskRunner,
        *,
        description: str,
        attached: bool,
    ) -> TaskSnapshot:
        """登记任务；有空位时立即运行，否则保持 queued。"""

        del prompt  # prompt 已由 runner 捕获，Manager 不读取模型内容。
        if self._closed:
            raise TaskManagerError("任务管理器已经关闭。")
        async with self._lock:
            if session.name:
                known = self._sessions_by_name.get(session.name)
                if known is not None and known is not session:
                    raise TaskManagerError(f"任务名称已存在：{session.name}")
                if known is session and self._session_is_busy(session):
                    raise TaskManagerError(f"任务仍在运行，不能继续发送消息：{session.name}")
                self._sessions_by_name[session.name] = session

            task_id = self._new_id()
            created = _now()
            record = _TaskRecord(
                id=task_id,
                name=session.name,
                description=description,
                kind=session.kind,
                session=session,
                runner=runner,
                status=TaskStatus.QUEUED,
                created_at=created,
                last_activity=created,
                attached=attached,
            )
            self._records[task_id] = record
            self._queue.append(task_id)
            self._publish_status(record, "queued")
            if bool(session.metadata.get("may_write")):
                self._events.append(
                    SubAgentEvent(
                        type="workspace_warning",
                        task_id=record.id,
                        task_name=record.name,
                        agent_name=record.session.agent_name,
                        attached=record.attached,
                        text="子 Agent 共享当前工作区，并行修改同一文件可能冲突。",
                        status=record.status,
                        running_count=self.running_count(),
                        queued_count=self.queued_count(),
                    )
                )
        await self._start_available()
        return self._snapshot(record)

    def _new_id(self) -> str:
        while True:
            task_id = f"task_{secrets.token_hex(4)}"
            if task_id not in self._records:
                return task_id

    def _session_is_busy(self, session: SubAgentSession) -> bool:
        return any(
            record.session is session and record.status in {TaskStatus.QUEUED, TaskStatus.RUNNING}
            for record in self._records.values()
        )

    async def _start_available(self) -> None:
        async with self._lock:
            while self._queue and len(self._running) < self.max_concurrent:
                task_id = self._queue.popleft()
                record = self._records.get(task_id)
                if record is None or record.status is not TaskStatus.QUEUED:
                    continue
                record.status = TaskStatus.RUNNING
                record.started_at = _now()
                record.last_activity = record.started_at
                record.started_event.set()
                self._running.add(task_id)
                self._publish_status(record, "running")
                record.task = asyncio.create_task(
                    self._run(record),
                    name=f"dragon-subagent-{task_id}",
                )

    async def _run(self, record: _TaskRecord) -> None:
        try:
            result = await record.runner(record.id)
        except asyncio.CancelledError:
            self._finish_record(record, TaskStatus.CANCELLED, error="任务已取消。")
        except Exception:
            self._finish_record(record, TaskStatus.FAILED, error="子 Agent 执行失败。")
        else:
            if result.stop_reason == "completed":
                self._finish_record(
                    record,
                    TaskStatus.COMPLETED,
                    result=result.text,
                    usage=result.usage,
                    tool_count=result.tool_count,
                )
            elif result.stop_reason == "cancelled":
                self._finish_record(
                    record,
                    TaskStatus.CANCELLED,
                    error=result.text or "任务已取消。",
                    usage=result.usage,
                    tool_count=result.tool_count,
                )
            else:
                self._finish_record(
                    record,
                    TaskStatus.FAILED,
                    error=result.text or "子 Agent 未正常完成。",
                    usage=result.usage,
                    tool_count=result.tool_count,
                )
        finally:
            async with self._lock:
                self._running.discard(record.id)
            record.done_event.set()
            await self._start_available()

    def _finish_record(
        self,
        record: _TaskRecord,
        status: TaskStatus,
        *,
        result: str = "",
        error: str = "",
        usage: TokenUsage | None = None,
        tool_count: int = 0,
    ) -> None:
        if record.status not in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
            return
        record.status = status
        record.finished_at = _now()
        record.last_activity = record.finished_at
        record.result = _truncate(self._safe_text(result), MAX_STORED_RESULT)
        record.error = _truncate(self._safe_text(error), MAX_NOTIFICATION)
        record.usage = usage or record.usage
        record.tool_count = max(tool_count, record.tool_count)
        self._publish_status(record, status.value)
        if not record.attached:
            self._reminders.append(self._build_notification(record))

    def publish_agent_event(self, task_id: str, event: AgentEvent) -> None:
        """给子 Agent 事件补上任务身份，供 TUI 区分显示。"""

        record = self._records.get(task_id)
        if record is None:
            return
        record.last_activity = _now()
        if event.type == "tool_start":
            record.tool_count += 1
        if event.usage is not None:
            record.usage = event.usage
        # Agent 自己的 completed/error 等事件到达时，Manager 还没有写入终态。
        # 终态统一由 _finish_record 发布，避免 TUI 看到“completed + running”的矛盾组合。
        if event.type in {"completed", "cancelled", "error", "limit", "user_rejected"}:
            return
        self._events.append(
            SubAgentEvent(
                type=event.type,
                task_id=record.id,
                task_name=record.name,
                agent_name=record.session.agent_name,
                attached=record.attached,
                text=event.text,
                tool_call=event.tool_call,
                tool_result=event.tool_result,
                usage=event.usage,
                status=record.status,
                iteration=event.iteration,
                max_iterations=event.max_iterations,
                running_count=self.running_count(),
                queued_count=self.queued_count(),
            )
        )

    async def wait_until_detached_or_done(
        self,
        task_id: str,
        timeout_seconds: float | None = None,
    ) -> TaskWaitOutcome:
        record = self._require(task_id)
        timeout = self.foreground_timeout if timeout_seconds is None else timeout_seconds

        # 排队期间也允许 Ctrl+B；真正的超时从 running 才开始计算。
        while not record.started_event.is_set():
            outcome = await self._wait_events(record, timeout=None, include_started=True)
            if outcome != "started":
                return TaskWaitOutcome(self._snapshot(record), outcome)

        outcome = await self._wait_events(record, timeout=timeout, include_started=False)
        if outcome == "timeout":
            self._detach(record, "timeout")
            outcome = "timeout"
        return TaskWaitOutcome(self._snapshot(record), outcome)

    async def _wait_events(
        self,
        record: _TaskRecord,
        *,
        timeout: float | None,
        include_started: bool,
    ) -> str:
        waits: dict[asyncio.Task[bool], str] = {
            asyncio.create_task(record.done_event.wait()): "done",
            asyncio.create_task(record.detached_event.wait()): record.detach_reason or "manual",
        }
        if include_started:
            waits[asyncio.create_task(record.started_event.wait())] = "started"
        done, pending = await asyncio.wait(
            waits,
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        if not done:
            return "timeout"
        finished = next(iter(done))
        return waits[finished]

    def move_foreground_to_background(self) -> str | None:
        """把最近的 attached 任务无损移交后台。"""

        for record in reversed(list(self._records.values())):
            if record.attached and record.status in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
                self._detach(record, "manual")
                return record.id
        return None

    def _detach(self, record: _TaskRecord, reason: str) -> None:
        if not record.attached:
            return
        record.attached = False
        record.detach_reason = reason
        record.last_activity = _now()
        record.detached_event.set()
        self._publish_status(record, f"{reason}_background")

    async def stop(self, task_id: str) -> TaskSnapshot:
        record = self._require(task_id)
        if record.status is TaskStatus.QUEUED:
            async with self._lock:
                try:
                    self._queue.remove(task_id)
                except ValueError:
                    pass
            self._finish_record(record, TaskStatus.CANCELLED, error="排队任务已取消。")
            record.done_event.set()
            return self._snapshot(record)
        if record.status is not TaskStatus.RUNNING:
            raise TaskManagerError(f"任务已经结束，不能取消：{task_id}")

        request_cancel = getattr(record.session.agent, "request_cancel", None)
        if request_cancel is not None:
            request_cancel()
        if record.task is not None:
            record.task.cancel()
            await asyncio.gather(record.task, return_exceptions=True)
        # create_task 后立刻取消时，协程可能尚未进入 _run 的 try/finally。
        # 这里补齐终态和并发槽，避免留下永久 running 的任务。
        if record.status is TaskStatus.RUNNING:
            self._finish_record(record, TaskStatus.CANCELLED, error="任务已取消。")
            async with self._lock:
                self._running.discard(record.id)
            record.done_event.set()
            await self._start_available()
        return self._snapshot(record)

    def session_for_continuation(self, name: str) -> SubAgentSession:
        """只允许继续当前会话中最后一次成功完成的命名子 Agent。"""

        session = self._sessions_by_name.get(name)
        if session is None:
            raise TaskManagerError(f"未知命名任务：{name}")
        records = [record for record in self._records.values() if record.session is session]
        if not records:
            raise TaskManagerError(f"命名任务没有执行记录：{name}")
        latest = records[-1]
        if latest.status in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
            raise TaskManagerError(f"任务仍在运行，不能继续发送消息：{name}")
        if latest.status is TaskStatus.CANCELLED:
            raise TaskManagerError(f"已取消任务不能继续发送消息：{name}")
        if latest.status is not TaskStatus.COMPLETED:
            raise TaskManagerError(f"任务未成功完成，不能继续发送消息：{name}")
        return session

    def get(self, task_id: str) -> TaskSnapshot | None:
        record = self._records.get(task_id)
        return self._snapshot(record) if record is not None else None

    def list(self) -> list[TaskSnapshot]:
        return [self._snapshot(record) for record in self._records.values()]

    def _require(self, task_id: str) -> _TaskRecord:
        record = self._records.get(task_id)
        if record is None:
            raise TaskManagerError(f"未知任务 ID：{task_id}")
        return record

    def _snapshot(self, record: _TaskRecord) -> TaskSnapshot:
        queued_position = None
        if record.status is TaskStatus.QUEUED:
            try:
                queued_position = list(self._queue).index(record.id) + 1
            except ValueError:
                queued_position = None
        return TaskSnapshot(
            id=record.id,
            name=record.name,
            description=record.description,
            kind=record.kind,
            status=record.status,
            created_at=record.created_at,
            started_at=record.started_at,
            finished_at=record.finished_at,
            result=_truncate(record.result, MAX_TASK_RESULT),
            error=record.error,
            usage=record.usage,
            tool_count=record.tool_count,
            last_activity=record.last_activity,
            attached=record.attached,
            queued_position=queued_position,
        )

    def _publish_status(self, record: _TaskRecord, event_type: str) -> None:
        self._events.append(
            SubAgentEvent(
                type=event_type,
                task_id=record.id,
                task_name=record.name,
                agent_name=record.session.agent_name,
                attached=record.attached,
                text=record.error or record.result,
                status=record.status,
                usage=record.usage,
                running_count=self.running_count(),
                queued_count=self.queued_count(),
            )
        )

    def _build_notification(self, record: _TaskRecord) -> str:
        summary = record.result if record.status is TaskStatus.COMPLETED else record.error
        summary = _truncate(summary, MAX_NOTIFICATION)
        return (
            "<task-notification>\n"
            f"task_id: {record.id}\n"
            f"name: {record.name or '-'}\n"
            f"status: {record.status.value}\n"
            f"summary: {summary}\n"
            "</task-notification>"
        )

    def drain_events(self) -> list[SubAgentEvent]:
        events = list(self._events)
        self._events.clear()
        return events

    def take_reminders(self) -> list[str]:
        reminders = list(self._reminders)
        self._reminders.clear()
        return reminders

    def running_count(self) -> int:
        return len(self._running)

    def queued_count(self) -> int:
        return sum(record.status is TaskStatus.QUEUED for record in self._records.values())

    async def reset_session(self) -> None:
        task_ids = [
            record.id
            for record in self._records.values()
            if record.status in {TaskStatus.QUEUED, TaskStatus.RUNNING}
        ]
        for task_id in task_ids:
            try:
                await self.stop(task_id)
            except TaskManagerError:
                continue
        self._records.clear()
        self._queue.clear()
        self._running.clear()
        self._sessions_by_name.clear()
        self._events.clear()
        self._reminders.clear()

    async def close(self) -> None:
        if self._closed:
            return
        await self.reset_session()
        self._closed = True
