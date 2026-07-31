"""工具分批、并发保序和取消测试。"""

import asyncio

from pydantic import BaseModel

from dragon_code.models import ToolCall
from dragon_code.tool_scheduler import ToolScheduler
from dragon_code.tools.base import Tool
from dragon_code.tools.registry import ToolRegistry


class EmptyArguments(BaseModel):
    pass


class RecordingTool(Tool):
    description = "调度测试工具"
    category = "test"
    arguments_model = EmptyArguments

    def __init__(self, name, *, safe=True, delay=0, finished=None, started=None, fail=False):
        self.name = name
        self.is_concurrency_safe = safe
        self.delay = delay
        self.finished = finished
        self.started = started
        self.fail = fail

    async def run(self, call, arguments):
        if self.started is not None:
            self.started.set()
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("broken")
        if self.finished is not None:
            self.finished.append(self.name)
        return self._success(call, self.name)


def make_scheduler(*tools):
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return ToolScheduler(registry)


def test_partition_keeps_safe_groups_and_unsafe_order():
    scheduler = make_scheduler(
        RecordingTool("Read", safe=True),
        RecordingTool("Glob", safe=True),
        RecordingTool("Edit", safe=False),
    )
    calls = [
        ToolCall("1", "Read", {}),
        ToolCall("2", "Glob", {}),
        ToolCall("3", "Edit", {}),
        ToolCall("4", "Read", {}),
        ToolCall("5", "Missing", {}),
    ]

    batches = scheduler.partition(calls)

    assert [batch.concurrent for batch in batches] == [True, False, True, False]
    assert [[call.id for call in batch.calls] for batch in batches] == [
        ["1", "2"],
        ["3"],
        ["4"],
        ["5"],
    ]


async def test_execute_batch_runs_concurrently_but_returns_original_order():
    finished = []
    scheduler = make_scheduler(
        RecordingTool("Slow", delay=0.03, finished=finished),
        RecordingTool("Fast", delay=0.001, finished=finished),
    )
    batch = scheduler.partition([ToolCall("1", "Slow", {}), ToolCall("2", "Fast", {})])[0]

    results = await scheduler.execute_batch(batch)

    assert finished == ["Fast", "Slow"]
    assert [result.call_id for result in results] == ["1", "2"]
    assert [result.content for result in results] == ["Slow", "Fast"]


async def test_execute_batch_keeps_other_result_when_one_tool_fails():
    scheduler = make_scheduler(
        RecordingTool("Good"),
        RecordingTool("Broken", fail=True),
    )
    batch = scheduler.partition([ToolCall("1", "Good", {}), ToolCall("2", "Broken", {})])[0]

    results = await scheduler.execute_batch(batch)

    assert results[0].success is True
    assert results[1].success is False
    assert scheduler.active_tasks == {}


async def test_cancel_active_marks_started_tool_unknown():
    started = asyncio.Event()
    scheduler = make_scheduler(RecordingTool("Slow", delay=10, started=started))
    batch = scheduler.partition([ToolCall("1", "Slow", {})])[0]
    batch_task = asyncio.create_task(scheduler.execute_batch(batch))

    await started.wait()
    scheduler.cancel_active()
    results = await batch_task

    assert results[0].error_code == "cancel_outcome_unknown"
    assert scheduler.active_tasks == {}


def test_make_cancelled_results_marks_unstarted_tools():
    scheduler = make_scheduler()
    results = scheduler.make_cancelled_results(
        [ToolCall("1", "Write", {}), ToolCall("2", "Bash", {})]
    )

    assert [result.error_code for result in results] == ["cancelled", "cancelled"]
