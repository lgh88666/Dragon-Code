"""匹配并编排当前生命周期事件的 Hook。"""

from __future__ import annotations

import asyncio

from dragon_code.hooks.actions import HookActionExecutor
from dragon_code.hooks.conditions import condition_matches
from dragon_code.hooks.models import (
    HookActionType,
    HookContext,
    HookDefinition,
    HookExecution,
    HookOutcome,
    HookSnapshot,
)


class HookEngine:
    """一个应用实例共享一个 HookEngine。"""

    def __init__(self, snapshot: HookSnapshot):
        self.snapshot = snapshot
        self.session_id = ""
        self._executed_once: set[str] = set()
        self._pending_reminders: list[str] = []
        self._background_tasks: set[asyncio.Task[HookExecution]] = set()
        self._background_results: list[HookExecution] = []
        self.executor = HookActionExecutor(self._pending_reminders.append)

    def begin_session(self, session_id: str) -> None:
        for task in self._background_tasks:
            if not task.done():
                task.cancel()
        self._background_tasks.clear()
        self._pending_reminders.clear()
        self._background_results.clear()
        self.session_id = session_id
        self._executed_once.clear()

    async def trigger(self, context: HookContext) -> HookOutcome:
        outcome = HookOutcome()
        for hook in self.snapshot.hooks:
            if hook.event is not context.event or not condition_matches(hook.condition, context):
                continue
            if hook.only_once and hook.name in self._executed_once:
                continue
            if hook.only_once:
                self._executed_once.add(hook.name)

            if hook.run_async:
                task = asyncio.create_task(self._run_background(hook, context))
                self._track_task(task)
                outcome.executions.append(
                    HookExecution(hook.name, hook.action.type, "scheduled", "Hook 已在后台运行。")
                )
                continue

            execution = await self.executor.execute(hook, context)
            outcome.executions.append(execution)
            if execution.blocked:
                outcome.blocked = True
                outcome.reason = execution.message
                break
        return outcome

    def _track_task(self, task: asyncio.Task[HookExecution]) -> None:
        self._background_tasks.add(task)

        def finished(done: asyncio.Task[HookExecution]) -> None:
            self._background_tasks.discard(done)
            if done.cancelled():
                return
            try:
                done.result()
            except Exception:
                # _run_background 已把普通失败包装成结果；这里只防止意外异常泄漏。
                self._background_results.append(
                    HookExecution("unknown", HookActionType.SHELL, "failed", "异步 Hook 执行失败。")
                )

        task.add_done_callback(finished)

    async def _run_background(
        self,
        hook: HookDefinition,
        context: HookContext,
    ) -> HookExecution:
        result = await self.executor.execute(hook, context)
        self._background_results.append(result)
        return result

    def take_reminders(self) -> list[str]:
        reminders = list(self._pending_reminders)
        self._pending_reminders.clear()
        return reminders

    def drain_background_results(self) -> list[HookExecution]:
        results = list(self._background_results)
        self._background_results.clear()
        return results

    async def close(self) -> None:
        """短暂等待后台任务，然后取消剩余任务，避免退出泄漏。"""

        tasks = list(self._background_tasks)
        if not tasks:
            return
        done, pending = await asyncio.wait(tasks, timeout=1.0)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            self._background_tasks.discard(task)
