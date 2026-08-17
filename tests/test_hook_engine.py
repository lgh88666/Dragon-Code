import asyncio
from pathlib import Path

from dragon_code.hooks import HookEngine
from dragon_code.hooks.models import (
    HookAction,
    HookActionType,
    HookContext,
    HookDefinition,
    HookEvent,
    HookExecution,
    HookSnapshot,
)


def hook(name, action, *, once=False, run_async=False):
    return HookDefinition(
        name,
        HookEvent.STOP,
        None,
        action,
        only_once=once,
        run_async=run_async,
        timeout=1,
    )


def context():
    return HookContext(HookEvent.STOP, "s1", Path.cwd(), "default")


def test_new_session_shares_snapshot_but_isolates_reminders():
    snapshot = HookSnapshot()
    parent = HookEngine(snapshot)
    parent.begin_session("parent")
    parent._pending_reminders.append("parent reminder")

    child = parent.new_session("child")

    assert child.snapshot is parent.snapshot
    assert child.session_id == "child"
    assert child.take_reminders() == []
    assert parent.take_reminders() == ["parent reminder"]


async def test_engine_runs_in_order_and_prompt_is_consumed_once():
    first = hook("one", HookAction(HookActionType.PROMPT, prompt="one"))
    second = hook("two", HookAction(HookActionType.SUBAGENT, task="two"))
    engine = HookEngine(HookSnapshot((first, second)))
    result = await engine.trigger(context())
    assert [item.hook_name for item in result.executions] == ["one", "two"]
    assert len(engine.take_reminders()) == 1
    assert engine.take_reminders() == []


async def test_only_once_resets_for_new_session():
    item = hook("once", HookAction(HookActionType.SUBAGENT, task="x"), once=True)
    engine = HookEngine(HookSnapshot((item,)))
    engine.begin_session("s1")
    assert len((await engine.trigger(context())).executions) == 1
    assert len((await engine.trigger(context())).executions) == 0
    engine.begin_session("s2")
    assert len((await engine.trigger(context())).executions) == 1


async def test_async_hook_is_tracked_and_drained():
    item = hook(
        "background",
        HookAction(HookActionType.SUBAGENT, task="x"),
        run_async=True,
    )
    engine = HookEngine(HookSnapshot((item,)))
    outcome = await engine.trigger(context())
    assert outcome.executions[0].status == "scheduled"
    await asyncio.sleep(0)
    results = engine.drain_background_results()
    assert results[0].status == "not_implemented"
    await engine.close()


async def test_failed_hook_does_not_stop_later_non_blocking_hook():
    class RecordingExecutor:
        def __init__(self):
            self.names = []

        async def execute(self, definition, _context):
            self.names.append(definition.name)
            status = "failed" if definition.name == "bad" else "success"
            return HookExecution(definition.name, definition.action.type, status)

    first = hook("bad", HookAction(HookActionType.SHELL, command="unused"))
    second = hook("good", HookAction(HookActionType.SHELL, command="unused"))
    engine = HookEngine(HookSnapshot((first, second)))
    recorder = RecordingExecutor()
    engine.executor = recorder

    outcome = await engine.trigger(context())

    assert recorder.names == ["bad", "good"]
    assert [item.status for item in outcome.executions] == ["failed", "success"]
