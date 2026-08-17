import asyncio
import json

from dragon_code.models import TokenUsage, ToolCall
from dragon_code.permissions import PermissionMode
from dragon_code.subagents.catalog import AgentCatalog
from dragon_code.subagents.manager import BackgroundTaskManager
from dragon_code.subagents.models import (
    AgentDefinition,
    AgentDefinitionSource,
    SubAgentKind,
    SubAgentLaunchOutcome,
    SubAgentResult,
    SubAgentSession,
)
from dragon_code.subagents.tools import (
    AgentTool,
    SendMessageTool,
    TaskGetTool,
    TaskListTool,
    TaskStopTool,
)


class FakeHost:
    def __init__(self):
        self.requests = []
        self.continuations = []

    async def launch(self, request, *, call=None):
        self.requests.append((request, call))
        return SubAgentLaunchOutcome("task_1234", "completed", "结果", False)

    async def continue_named(self, name, prompt):
        self.continuations.append((name, prompt))
        return SubAgentLaunchOutcome("task_next", "running", background=True)


def catalog():
    item = AgentDefinition(
        "explore",
        "探索代码",
        "只读",
        (),
        (),
        "deepseek-v4-flash",
        10,
        PermissionMode.PLAN,
        False,
        AgentDefinitionSource.BUILTIN,
        __file__,
    )
    return AgentCatalog((item,))


def call(name, arguments):
    return ToolCall(f"call-{name}", name, arguments)


async def test_agent_tool_selects_defined_and_fork_paths():
    host = FakeHost()
    tool = AgentTool(catalog(), host)

    defined = await tool.execute(
        call(
            "Agent",
            {"prompt": "探索", "description": "任务", "role": "explore"},
        )
    )
    forked = await tool.execute(call("Agent", {"prompt": "继续", "description": "Fork"}))

    assert defined.success and forked.success
    assert host.requests[0][0].kind is SubAgentKind.DEFINED
    assert host.requests[1][0].kind is SubAgentKind.FORK
    assert json.loads(defined.content)["result"] == "结果"
    assert "explore: 探索代码" in tool.description


async def test_agent_tool_returns_validation_error():
    result = await AgentTool(catalog(), FakeHost()).execute(
        call("Agent", {"prompt": "", "description": ""})
    )

    assert not result.success
    assert result.error_code == "invalid_arguments"


async def test_task_tools_list_get_stop_and_send_message():
    manager = BackgroundTaskManager()
    release = asyncio.Event()

    class Agent:
        def request_cancel(self):
            pass

    session = SubAgentSession(
        "key",
        "named",
        SubAgentKind.DEFINED,
        "explore",
        Agent(),
        object(),
        object(),
    )

    async def runner(_task_id):
        await release.wait()
        return SubAgentResult("完成", TokenUsage(2, 1), 0, "completed")

    task = await manager.submit(session, "prompt", runner, description="测试任务", attached=False)
    listed = await TaskListTool(manager).execute(call("TaskList", {}))
    fetched = await TaskGetTool(manager).execute(call("TaskGet", {"task_id": task.id}))
    host = FakeHost()
    continued = await SendMessageTool(host).execute(
        call("SendMessage", {"name": "named", "prompt": "继续"})
    )
    stopped = await TaskStopTool(manager).execute(call("TaskStop", {"task_id": task.id}))

    assert json.loads(listed.content)["running"] == 1
    assert json.loads(fetched.content)["id"] == task.id
    assert json.loads(continued.content)["task_id"] == "task_next"
    assert stopped.success
    await manager.close()


async def test_task_get_unknown_id_is_structured_error():
    manager = BackgroundTaskManager()
    result = await TaskGetTool(manager).execute(call("TaskGet", {"task_id": "task_missing"}))

    assert not result.success
    assert result.error_code == "unknown_task"
    await manager.close()
