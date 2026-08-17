import asyncio
from pathlib import Path

from dragon_code.agent import Agent
from dragon_code.clients.base import LLMClient
from dragon_code.models import (
    ChatMessage,
    LLMEvent,
    ProviderConfig,
    SystemPrompt,
    TokenUsage,
    ToolCall,
)
from dragon_code.permissions import PermissionMode
from dragon_code.session import Conversation
from dragon_code.subagents.catalog import AgentCatalog
from dragon_code.subagents.host import SubAgentHost
from dragon_code.subagents.manager import BackgroundTaskManager
from dragon_code.subagents.models import (
    AgentDefinition,
    AgentDefinitionSource,
    SubAgentKind,
    SubAgentLaunchRequest,
    TaskStatus,
)
from dragon_code.tools.registry import create_default_registry


class ResponseClient(LLMClient):
    def __init__(self, config: ProviderConfig, responses):
        super().__init__(config)
        self.responses = list(responses)
        self.requests = []

    async def stream(self, request):
        self.requests.append(request)
        for event in self.responses.pop(0):
            yield event


def final_response(text="完成"):
    return [
        LLMEvent("usage", usage=TokenUsage(5, 2)),
        LLMEvent("completed", message=ChatMessage("assistant", content=text)),
    ]


def tool_response(call: ToolCall):
    return [
        LLMEvent("tool_call", tool_call=call),
        LLMEvent(
            "completed",
            message=ChatMessage("assistant", tool_calls=[call]),
        ),
    ]


def definition(*, tools=("Read", "Glob", "Grep"), mode=PermissionMode.PLAN):
    return AgentDefinition(
        name="explore",
        description="探索代码",
        system_prompt="只读探索代码。",
        allowed_tools=tuple(tools),
        disallowed_tools=(),
        model="deepseek-v4-flash",
        max_iterations=10,
        permission_mode=mode,
        background=False,
        source=AgentDefinitionSource.BUILTIN,
        source_path=Path("explore.md"),
    )


def parent_agent(tmp_path, client, conversation=None):
    agent = Agent(
        client,
        conversation or Conversation(),
        create_default_registry(tmp_path),
        tmp_path,
        "test",
    )
    agent.current_system_prompt = SystemPrompt("stable-parent", "environment")
    return agent


async def wait_terminal(manager, task_id):
    for _ in range(200):
        snapshot = manager.get(task_id)
        if snapshot.status in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }:
            return snapshot
        await asyncio.sleep(0.001)
    raise AssertionError("任务没有结束")


async def test_defined_subagent_uses_blank_history_and_default_model(tmp_path):
    parent_client = ResponseClient(
        ProviderConfig("Main", "openai", "key", "parent-model"),
        [],
    )
    created = []

    def factory(config):
        client = ResponseClient(config, [final_response("探索完成")])
        created.append(client)
        return client

    manager = BackgroundTaskManager()
    host = SubAgentHost(AgentCatalog((definition(),)), manager, factory)
    parent = parent_agent(
        tmp_path,
        parent_client,
        Conversation([ChatMessage("user", content="主历史")]),
    )
    host.bind_parent(parent)

    outcome = await host.launch(
        SubAgentLaunchRequest(
            "查看结构",
            "探索",
            role_name="explore",
            task_name="reader",
        )
    )

    assert outcome.status == "completed"
    assert outcome.text == "探索完成"
    assert created[0].model == "deepseek-v4-flash"
    assert [item.content for item in created[0].requests[0].messages] == ["查看结构"]
    assert parent.conversation.get_messages()[0].content == "主历史"
    await manager.close()
    await host.close()


async def test_fork_inherits_parent_prefix_and_runs_in_background(tmp_path):
    parent_client = ResponseClient(
        ProviderConfig("Main", "anthropic", "key", "parent-model"),
        [final_response("Fork 完成")],
    )
    manager = BackgroundTaskManager()
    host = SubAgentHost(AgentCatalog((definition(),)), manager, lambda config: parent_client)
    parent = parent_agent(
        tmp_path,
        parent_client,
        Conversation(
            [
                ChatMessage("user", content="记住 dragon"),
                ChatMessage("assistant", content="已记住"),
            ]
        ),
    )
    parent.pending_assistant_message = ChatMessage(
        "assistant",
        tool_calls=[ToolCall("agent_call", "Agent", {"prompt": "分析"})],
    )
    host.bind_parent(parent)

    outcome = await host.launch(
        SubAgentLaunchRequest(
            "分析前文",
            "Fork",
            model_override="ignored-model",
            kind=SubAgentKind.FORK,
        ),
        call=parent.pending_assistant_message.tool_calls[0],
    )
    snapshot = await wait_terminal(manager, outcome.task_id)

    assert outcome.background is True
    assert snapshot.status is TaskStatus.COMPLETED
    request = parent_client.requests[0]
    assert request.system.stable == "stable-parent"
    assert [tool.name for tool in request.tools] == parent.registry.names()
    assert "<fork-boilerplate>" in request.messages[-1].content
    assert request.messages[-2].tool_results[0].call_id == "agent_call"
    assert parent_client.model == "parent-model"
    await manager.close()
    await host.close()


async def test_send_message_appends_new_prompt_to_completed_named_fork(tmp_path):
    parent_client = ResponseClient(
        ProviderConfig("Main", "anthropic", "key", "parent-model"),
        [final_response("第一次完成"), final_response("续派完成")],
    )
    manager = BackgroundTaskManager()
    host = SubAgentHost(AgentCatalog((definition(),)), manager, lambda config: parent_client)
    parent = parent_agent(tmp_path, parent_client)
    host.bind_parent(parent)

    first = await host.launch(
        SubAgentLaunchRequest(
            "第一次任务",
            "Fork",
            task_name="named-fork",
            kind=SubAgentKind.FORK,
        )
    )
    await wait_terminal(manager, first.task_id)
    second = await host.continue_named("named-fork", "这是续派的新任务")
    snapshot = await wait_terminal(manager, second.task_id)

    assert snapshot.result == "续派完成"
    assert "这是续派的新任务" in parent_client.requests[1].messages[-1].content
    assert first.task_id != second.task_id
    await manager.close()
    await host.close()


async def test_child_ask_is_structured_denial_without_permission_event(tmp_path):
    write_call = ToolCall("write_1", "Write", {"path": "a.txt", "content": "x"})
    parent_client = ResponseClient(
        ProviderConfig("Main", "openai", "key", "parent"),
        [],
    )
    child_client = ResponseClient(
        ProviderConfig("Main", "openai", "key", "deepseek-v4-flash"),
        [tool_response(write_call), final_response("已改用安全方案")],
    )
    manager = BackgroundTaskManager()
    writable = definition(tools=("Write",), mode=PermissionMode.DEFAULT)
    host = SubAgentHost(AgentCatalog((writable,)), manager, lambda _config: child_client)
    host.bind_parent(parent_agent(tmp_path, parent_client))

    outcome = await host.launch(SubAgentLaunchRequest("尝试写入", "权限", role_name="explore"))

    assert outcome.status == "completed"
    assert not (tmp_path / "a.txt").exists()
    tool_message = child_client.requests[1].messages[-1]
    assert tool_message.tool_results[0].error_code == "permission_denied"
    assert not any(event.type == "permission_request" for event in manager.drain_events())
    await manager.close()
    await host.close()
