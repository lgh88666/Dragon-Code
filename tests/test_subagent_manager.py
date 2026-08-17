import asyncio

import pytest

from dragon_code.models import AgentEvent, TokenUsage, ToolCall
from dragon_code.subagents.manager import BackgroundTaskManager, TaskManagerError
from dragon_code.subagents.models import (
    SubAgentKind,
    SubAgentResult,
    SubAgentSession,
    TaskStatus,
)


class FakeAgent:
    def __init__(self):
        self.cancelled = False

    def request_cancel(self):
        self.cancelled = True


def session(name: str = "") -> SubAgentSession:
    return SubAgentSession(
        key=f"key-{name or id(name)}",
        name=name,
        kind=SubAgentKind.DEFINED,
        agent_name="explore",
        agent=FakeAgent(),
        conversation=object(),
        hook_engine=object(),
    )


async def completed_result(text: str = "done") -> SubAgentResult:
    return SubAgentResult(text, TokenUsage(3, 2), 1, "completed")


async def wait_for_status(manager, task_id, status):
    for _ in range(100):
        snapshot = manager.get(task_id)
        if snapshot is not None and snapshot.status is status:
            return snapshot
        await asyncio.sleep(0.001)
    raise AssertionError(f"任务没有进入 {status}")


async def test_manager_completes_and_notifies_background_task():
    manager = BackgroundTaskManager()

    async def runner(_task_id):
        return await completed_result("结果")

    task = await manager.submit(
        session("one"), "prompt", runner, description="测试", attached=False
    )
    snapshot = await wait_for_status(manager, task.id, TaskStatus.COMPLETED)

    assert snapshot.result == "结果"
    assert snapshot.usage.total_tokens == 5
    reminders = manager.take_reminders()
    assert len(reminders) == 1
    assert task.id in reminders[0]
    assert manager.take_reminders() == []
    await manager.close()


async def test_writable_task_warns_and_redacts_sensitive_result():
    manager = BackgroundTaskManager()
    manager.add_sensitive_value("secret-key")
    writable = session("writer")
    writable.metadata["may_write"] = True

    async def runner(_task_id):
        return await completed_result("结果包含 secret-key")

    task = await manager.submit(
        writable,
        "prompt",
        runner,
        description="写入任务",
        attached=False,
    )
    snapshot = await wait_for_status(manager, task.id, TaskStatus.COMPLETED)
    events = manager.drain_events()
    reminder = "\n".join(manager.take_reminders())

    assert any(event.type == "workspace_warning" for event in events)
    assert "secret-key" not in snapshot.result
    assert "[REDACTED]" in snapshot.result
    assert "secret-key" not in reminder
    await manager.close()


async def test_manager_limits_concurrency_and_uses_fifo():
    manager = BackgroundTaskManager(max_concurrent=3)
    release = [asyncio.Event() for _ in range(4)]
    started: list[int] = []
    tasks = []

    for index in range(4):

        async def runner(_task_id, current=index):
            started.append(current)
            await release[current].wait()
            return await completed_result(str(current))

        tasks.append(
            await manager.submit(
                session(f"task-{index}"),
                "prompt",
                runner,
                description=str(index),
                attached=False,
            )
        )

    await asyncio.sleep(0)
    assert started == [0, 1, 2]
    assert manager.get(tasks[3].id).status is TaskStatus.QUEUED

    release[1].set()
    await wait_for_status(manager, tasks[1].id, TaskStatus.COMPLETED)
    await wait_for_status(manager, tasks[3].id, TaskStatus.RUNNING)
    assert started == [0, 1, 2, 3]

    for event in release:
        event.set()
    await manager.close()


async def test_queued_task_can_be_cancelled_without_running():
    manager = BackgroundTaskManager(max_concurrent=1)
    release = asyncio.Event()
    calls = 0

    async def blocking(_task_id):
        await release.wait()
        return await completed_result()

    async def queued(_task_id):
        nonlocal calls
        calls += 1
        return await completed_result()

    first = await manager.submit(
        session("first"), "prompt", blocking, description="first", attached=False
    )
    second = await manager.submit(
        session("second"), "prompt", queued, description="second", attached=False
    )

    stopped = await manager.stop(second.id)
    assert stopped.status is TaskStatus.CANCELLED
    assert calls == 0
    release.set()
    await wait_for_status(manager, first.id, TaskStatus.COMPLETED)
    await manager.close()


async def test_manual_detach_does_not_restart_runner():
    manager = BackgroundTaskManager()
    release = asyncio.Event()
    calls = 0

    async def runner(_task_id):
        nonlocal calls
        calls += 1
        await release.wait()
        return await completed_result()

    task = await manager.submit(
        session("manual"), "prompt", runner, description="manual", attached=True
    )
    wait_task = asyncio.create_task(manager.wait_until_detached_or_done(task.id))
    await wait_for_status(manager, task.id, TaskStatus.RUNNING)

    assert manager.move_foreground_to_background() == task.id
    outcome = await wait_task
    assert outcome.reason == "manual"
    assert not outcome.task.attached
    assert calls == 1

    release.set()
    await wait_for_status(manager, task.id, TaskStatus.COMPLETED)
    assert calls == 1
    await manager.close()


async def test_timeout_detach_does_not_cancel_runner():
    manager = BackgroundTaskManager(foreground_timeout=0.01)
    release = asyncio.Event()
    calls = 0

    async def runner(_task_id):
        nonlocal calls
        calls += 1
        await release.wait()
        return await completed_result()

    task = await manager.submit(
        session("timeout"), "prompt", runner, description="timeout", attached=True
    )
    outcome = await manager.wait_until_detached_or_done(task.id)

    assert outcome.reason == "timeout"
    assert manager.get(task.id).status is TaskStatus.RUNNING
    assert calls == 1
    release.set()
    await manager.close()


async def test_publish_agent_event_updates_tool_count_and_usage():
    manager = BackgroundTaskManager()
    release = asyncio.Event()

    async def runner(_task_id):
        await release.wait()
        return await completed_result()

    task = await manager.submit(
        session("events"), "prompt", runner, description="events", attached=True
    )
    manager.publish_agent_event(
        task.id,
        AgentEvent(type="tool_start", tool_call=ToolCall("c1", "Read", {"path": "a"})),
    )
    manager.publish_agent_event(task.id, AgentEvent(type="usage", usage=TokenUsage(7, 4)))
    manager.publish_agent_event(task.id, AgentEvent(type="completed", text="尚未写入终态"))

    assert manager.get(task.id).tool_count == 1
    assert manager.get(task.id).usage.total_tokens == 11
    events = manager.drain_events()
    assert any(event.type == "tool_start" for event in events)
    assert not any(event.type == "completed" for event in events)
    release.set()
    await manager.close()


async def test_duplicate_name_and_unknown_stop_return_clear_errors():
    manager = BackgroundTaskManager()
    release = asyncio.Event()

    async def runner(_task_id):
        await release.wait()
        return await completed_result()

    await manager.submit(session("same"), "prompt", runner, description="one", attached=False)
    with pytest.raises(TaskManagerError, match="名称已存在"):
        await manager.submit(session("same"), "prompt", runner, description="two", attached=False)
    with pytest.raises(TaskManagerError, match="未知任务"):
        await manager.stop("task_missing")
    release.set()
    await manager.close()


async def test_only_completed_named_session_can_continue():
    manager = BackgroundTaskManager(max_concurrent=1)
    named = session("named")

    async def completed(_task_id):
        return await completed_result()

    task = await manager.submit(
        named,
        "prompt",
        completed,
        description="completed",
        attached=False,
    )
    await wait_for_status(manager, task.id, TaskStatus.COMPLETED)
    assert manager.session_for_continuation("named") is named

    blocked = asyncio.Event()

    async def waiting(_task_id):
        await blocked.wait()
        return await completed_result()

    busy = await manager.submit(
        named,
        "prompt",
        waiting,
        description="busy",
        attached=False,
    )
    with pytest.raises(TaskManagerError, match="仍在运行"):
        manager.session_for_continuation("named")
    await manager.stop(busy.id)
    with pytest.raises(TaskManagerError, match="已取消"):
        manager.session_for_continuation("named")
    with pytest.raises(TaskManagerError, match="未知命名任务"):
        manager.session_for_continuation("missing")
    await manager.close()


async def test_close_cancels_running_and_queued_tasks():
    manager = BackgroundTaskManager(max_concurrent=1)
    never = asyncio.Event()

    async def runner(_task_id):
        await never.wait()
        return await completed_result()

    first = await manager.submit(
        session("close-1"), "prompt", runner, description="one", attached=False
    )
    second = await manager.submit(
        session("close-2"), "prompt", runner, description="two", attached=False
    )

    await manager.close()

    assert manager.get(first.id) is None
    assert manager.get(second.id) is None
