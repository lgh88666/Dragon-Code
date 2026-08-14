"""按安全性分批执行模型一次回复中的多个工具调用。"""

import asyncio
from dataclasses import dataclass

from dragon_code.models import ToolCall, ToolResult
from dragon_code.tools.registry import ToolRegistry


@dataclass
class ToolBatch:
    """一组可以一起启动，或必须单独执行的工具调用。"""

    calls: list[ToolCall]
    concurrent: bool


class ToolScheduler:
    """负责工具分批、结果保序和尽力取消。"""

    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self.active_tasks: dict[str, asyncio.Task] = {}

    def partition(self, calls: list[ToolCall]) -> list[ToolBatch]:
        """连续安全工具并发；不安全和未知工具各自串行。"""

        batches: list[ToolBatch] = []
        safe_calls: list[ToolCall] = []

        for call in calls:
            tool = self.registry.get(call.name)
            is_skill_tool = call.name.startswith("skill__")
            if tool is not None and tool.is_concurrency_safe and not is_skill_tool:
                safe_calls.append(call)
                continue

            if safe_calls:
                batches.append(ToolBatch(calls=safe_calls, concurrent=True))
                safe_calls = []
            batches.append(ToolBatch(calls=[call], concurrent=False))

        if safe_calls:
            batches.append(ToolBatch(calls=safe_calls, concurrent=True))
        return batches

    async def execute_batch(self, batch: ToolBatch) -> list[ToolResult]:
        """执行一个批次，并按模型给出的调用顺序返回结果。"""

        tasks = []
        for call in batch.calls:
            task = asyncio.create_task(self.registry.execute(call))
            self.active_tasks[call.id] = task
            tasks.append(task)

        try:
            values = await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            self.active_tasks.clear()

        results = []
        for call, value in zip(batch.calls, values, strict=True):
            if isinstance(value, asyncio.CancelledError):
                results.append(self._unknown_cancel_result(call))
            elif isinstance(value, BaseException):
                results.append(
                    ToolResult(
                        call_id=call.id,
                        tool_name=call.name,
                        success=False,
                        error_code="tool_error",
                        error_message="工具执行发生未知错误。",
                    )
                )
            else:
                results.append(value)
        return results

    def cancel_active(self) -> None:
        """向当前已经启动、尚未结束的工具发送取消信号。"""

        for task in self.active_tasks.values():
            if not task.done():
                task.cancel()

    def make_cancelled_results(self, calls: list[ToolCall]) -> list[ToolResult]:
        """为确定尚未启动的工具生成取消结果。"""

        return [
            ToolResult(
                call_id=call.id,
                tool_name=call.name,
                success=False,
                error_code="cancelled",
                error_message="用户取消了任务，工具尚未执行。",
            )
            for call in calls
        ]

    @staticmethod
    def _unknown_cancel_result(call: ToolCall) -> ToolResult:
        return ToolResult(
            call_id=call.id,
            tool_name=call.name,
            success=False,
            error_code="cancel_outcome_unknown",
            error_message="已请求取消工具，但无法确认底层操作是否已经完成。",
        )
