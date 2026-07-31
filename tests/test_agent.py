"""Agent Loop、停止条件、取消和模式测试。"""

import asyncio

from pydantic import BaseModel

from dragon_code.agent import Agent
from dragon_code.models import (
    ChatMessage,
    ProviderConfig,
    ProviderEvent,
    TokenUsage,
    ToolCall,
)
from dragon_code.providers.base import BaseProvider, ProviderError
from dragon_code.session import Conversation
from dragon_code.tools.base import Tool
from dragon_code.tools.registry import ToolRegistry, create_default_registry


class EmptyArguments(BaseModel):
    pass


class DemoTool(Tool):
    description = "Agent 测试工具"
    category = "test"
    arguments_model = EmptyArguments

    def __init__(self, name="Demo", *, safe=True, started=None, delay=0, fail=False):
        self.name = name
        self.is_concurrency_safe = safe
        self.started = started
        self.delay = delay
        self.fail = fail
        self.calls = []

    async def run(self, call, arguments):
        self.calls.append(call.id)
        if self.started is not None:
            self.started.set()
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("测试工具主动失败")
        return self._success(call, f"result-{call.id}")


class SequenceProvider(BaseProvider):
    def __init__(self, responses):
        super().__init__(ProviderConfig("Fake", "openai", "key", "model"))
        self.responses = list(responses)
        self.requests = []

    async def stream(self, messages, system_prompt, tools):
        self.requests.append(
            {
                "messages": list(messages),
                "system_prompt": system_prompt,
                "tools": list(tools),
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        for event in response:
            yield event


class BlockingProvider(BaseProvider):
    def __init__(self):
        super().__init__(ProviderConfig("Fake", "openai", "key", "model"))
        self.started = asyncio.Event()
        self.closed = False

    async def stream(self, messages, system_prompt, tools):
        try:
            self.started.set()
            yield ProviderEvent("text_delta", text="部分")
            await asyncio.sleep(10)
        finally:
            self.closed = True


def response(content="", calls=None, usage=(10, 2)):
    calls = calls or []
    events = [ProviderEvent("tool_call", tool_call=call) for call in calls]
    events.extend(
        [
            ProviderEvent("usage", usage=TokenUsage(*usage)),
            ProviderEvent(
                "completed",
                message=ChatMessage("assistant", content=content, tool_calls=calls),
            ),
        ]
    )
    return events


def registry_with(*tools):
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


async def collect(agent, text="执行"):
    return [event async for event in agent.run(text)]


async def test_natural_plain_response_commits_once():
    provider = SequenceProvider([response("完成")])
    conversation = Conversation()
    agent = Agent(provider, conversation, "系统", ToolRegistry())

    events = await collect(agent)

    assert [event.type for event in events] == [
        "progress",
        "usage",
        "completed",
    ]
    assert len(provider.requests) == 1
    assert [item.role for item in conversation.get_messages()] == ["user", "assistant"]
    assert events[-1].usage == TokenUsage(10, 2)


async def test_multi_tool_loop_uses_complete_history():
    tool = DemoTool()
    first = ToolCall("1", "Demo", {})
    second = ToolCall("2", "Demo", {})
    provider = SequenceProvider(
        [
            response(calls=[first]),
            response(calls=[second]),
            response("最终", usage=(5, 1)),
        ]
    )
    conversation = Conversation()
    agent = Agent(provider, conversation, "系统", registry_with(tool))

    events = await collect(agent)

    assert tool.calls == ["1", "2"]
    assert len(provider.requests) == 3
    assert [item.role for item in conversation.get_messages()] == [
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
        "assistant",
    ]
    assert [event.type for event in events].count("tool_start") == 2
    assert events[-1].type == "completed"
    assert events[-1].usage == TokenUsage(25, 5)


async def test_event_order_follows_real_work_order():
    tool = DemoTool()
    call = ToolCall("1", "Demo", {})
    provider = SequenceProvider(
        [
            [
                ProviderEvent("text_delta", text="先检查"),
                *response(calls=[call]),
            ],
            [
                ProviderEvent("text_delta", text="已完成"),
                *response("已完成"),
            ],
        ]
    )
    agent = Agent(provider, Conversation(), "系统", registry_with(tool))

    events = await collect(agent)

    assert [event.type for event in events] == [
        "progress",
        "text",
        "usage",
        "tool_start",
        "tool_end",
        "progress",
        "text",
        "usage",
        "completed",
    ]


async def test_tool_failure_is_returned_and_agent_continues():
    broken = DemoTool("Broken", fail=True)
    provider = SequenceProvider(
        [
            response(calls=[ToolCall("1", "Broken", {})]),
            response("已根据失败结果调整"),
        ]
    )
    agent = Agent(provider, Conversation(), "系统", registry_with(broken))

    events = await collect(agent)

    result = next(event.tool_result for event in events if event.type == "tool_end")
    assert result.success is False
    assert result.error_code == "tool_error"
    assert events[-1].type == "completed"
    assert len(provider.requests) == 2


async def test_unknown_tool_limit_and_history_pairing():
    provider = SequenceProvider(
        [
            response(calls=[ToolCall("1", "Missing", {})]),
            response(calls=[ToolCall("2", "Missing", {})]),
            response(calls=[ToolCall("3", "Missing", {})]),
        ]
    )
    conversation = Conversation()
    agent = Agent(
        provider,
        conversation,
        "系统",
        ToolRegistry(),
        unknown_tool_limit=3,
    )

    events = await collect(agent)

    assert len(provider.requests) == 3
    assert events[-1].type == "limit"
    tool_messages = [item for item in conversation.get_messages() if item.role == "tool"]
    assert [item.tool_results[0].call_id for item in tool_messages] == ["1", "2", "3"]


async def test_valid_tool_resets_unknown_counter():
    demo = DemoTool()
    provider = SequenceProvider(
        [
            response(calls=[ToolCall("1", "Missing", {})]),
            response(calls=[ToolCall("2", "Missing", {})]),
            response(calls=[ToolCall("3", "Demo", {})]),
            response(calls=[ToolCall("4", "Missing", {})]),
            response(calls=[ToolCall("5", "Missing", {})]),
            response("完成"),
        ]
    )
    agent = Agent(provider, Conversation(), "系统", registry_with(demo))

    events = await collect(agent)

    assert events[-1].type == "completed"
    assert len(provider.requests) == 6


async def test_iteration_limit_executes_last_tools_without_extra_request():
    demo = DemoTool()
    provider = SequenceProvider(
        [
            response(calls=[ToolCall("1", "Demo", {})]),
            response(calls=[ToolCall("2", "Demo", {})]),
        ]
    )
    conversation = Conversation()
    agent = Agent(
        provider,
        conversation,
        "系统",
        registry_with(demo),
        max_iterations=2,
    )

    events = await collect(agent)

    assert demo.calls == ["1", "2"]
    assert len(provider.requests) == 2
    assert events[-1].type == "limit"
    assert conversation.get_messages()[-1].tool_results[0].call_id == "2"


async def test_stream_error_does_not_commit_incomplete_turn():
    error = ProviderError("network", "网络错误")
    conversation = Conversation()
    agent = Agent(SequenceProvider([error]), conversation, "系统", ToolRegistry())

    events = await collect(agent)

    assert events[-1].type == "error"
    assert conversation.get_messages() == []


async def test_provider_cancel_discards_partial_response():
    provider = BlockingProvider()
    conversation = Conversation()
    agent = Agent(provider, conversation, "系统", ToolRegistry())
    events = []

    async def consume():
        async for event in agent.run("慢回复"):
            events.append(event)

    task = asyncio.create_task(consume())
    await provider.started.wait()
    await asyncio.sleep(0)
    agent.request_cancel()
    await task

    assert events[-1].type == "cancelled"
    assert conversation.get_messages() == []
    assert provider.closed is True
    assert agent.active_provider_task is None


async def test_tool_cancel_keeps_real_unknown_and_unstarted_results():
    slow_started = asyncio.Event()
    fast = DemoTool("Fast", safe=False)
    slow = DemoTool("Slow", safe=False, started=slow_started, delay=10)
    later = DemoTool("Later", safe=False)
    calls = [
        ToolCall("1", "Fast", {}),
        ToolCall("2", "Slow", {}),
        ToolCall("3", "Later", {}),
    ]
    provider = SequenceProvider([response(calls=calls)])
    conversation = Conversation()
    agent = Agent(
        provider,
        conversation,
        "系统",
        registry_with(fast, slow, later),
    )
    events = []

    async def consume():
        async for event in agent.run("取消工具"):
            events.append(event)

    task = asyncio.create_task(consume())
    await slow_started.wait()
    agent.request_cancel()
    await task

    tool_message = conversation.get_messages()[-1]
    assert [result.error_code for result in tool_message.tool_results] == [
        "",
        "cancel_outcome_unknown",
        "cancelled",
    ]
    assert events[-1].type == "cancelled"
    assert agent.scheduler.active_tasks == {}
    assert later.calls == []


async def test_plan_mode_uses_only_read_tools_and_marks_plan_ready(tmp_path):
    provider = SequenceProvider([response("计划")])
    agent = Agent(
        provider,
        Conversation(),
        "基础系统提示",
        create_default_registry(tmp_path),
    )
    agent.enter_plan_mode()

    events = await collect(agent, "分析项目")

    assert events[-1].type == "completed"
    assert agent.can_execute_plan() is True
    assert [tool.name for tool in provider.requests[0]["tools"]] == ["Read", "Glob", "Grep"]
    assert "Plan Mode" in provider.requests[0]["system_prompt"]
    agent.enter_default_mode()
    assert agent.can_execute_plan() is False


async def test_plan_mode_does_not_execute_hallucinated_write(tmp_path):
    target = tmp_path / "should-not-exist.txt"
    write_call = ToolCall(
        "write-1",
        "Write",
        {"path": target.name, "content": "禁止写入"},
    )
    provider = SequenceProvider(
        [
            response(calls=[write_call]),
            response("只输出计划"),
        ]
    )
    agent = Agent(
        provider,
        Conversation(),
        "系统",
        create_default_registry(tmp_path),
    )
    agent.enter_plan_mode()

    events = await collect(agent, "先规划")

    result = next(event.tool_result for event in events if event.type == "tool_end")
    assert result.error_code == "unknown_tool"
    assert target.exists() is False
    assert events[-1].type == "completed"
