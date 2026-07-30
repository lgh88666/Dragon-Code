"""Conversation 与单轮工具闭环测试。"""

from conftest import FakeProvider
from pydantic import BaseModel

from dragon_code.models import ChatMessage, ProviderConfig, ProviderEvent, ToolCall
from dragon_code.providers.base import BaseProvider, ProviderError
from dragon_code.session import LIMIT_MESSAGE, ChatSession, Conversation
from dragon_code.tools.base import Tool
from dragon_code.tools.registry import ToolRegistry


class EmptyArguments(BaseModel):
    pass


class RecordingTool(Tool):
    name = "Demo"
    description = "测试工具"
    category = "test"
    arguments_model = EmptyArguments

    def __init__(self, records, name="Demo", fail=False):
        self.records = records
        self.name = name
        self.fail = fail

    async def run(self, call, arguments):
        self.records.append(call.id)
        if self.fail:
            return self._failure(call, "failed", "主动失败")
        return self._success(call, f"result-{call.id}")


class SequenceProvider(BaseProvider):
    def __init__(self, responses):
        super().__init__(ProviderConfig("Fake", "openai", "key", "model"))
        self.responses = list(responses)
        self.requests = []

    async def stream(self, messages, system_prompt, tools):
        self.requests.append(list(messages))
        for event in self.responses.pop(0):
            yield event


def completed(content="", calls=None):
    calls = calls or []
    events = [ProviderEvent("tool_call", tool_call=call) for call in calls]
    events.append(
        ProviderEvent(
            "completed",
            message=ChatMessage("assistant", content=content, tool_calls=calls),
        )
    )
    return events


def registry_with(*tools):
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


def test_conversation_returns_copy_and_commits_in_order():
    conversation = Conversation()
    request = conversation.build_request_messages("第一问")
    assert request == [ChatMessage("user", "第一问")]
    conversation.commit_messages(
        [ChatMessage("user", "第一问"), ChatMessage("assistant", "第一答")]
    )
    copied = conversation.get_messages()
    copied.clear()
    assert [item.role for item in conversation.get_messages()] == ["user", "assistant"]


async def test_plain_session_streams_and_commits():
    provider = FakeProvider(chunks=["你", "好"])
    conversation = Conversation()
    session = ChatSession(provider, conversation, "系统", ToolRegistry())
    events = [event async for event in session.stream_turn("问候")]
    assert [event.type for event in events] == ["text", "text", "completed"]
    assert conversation.get_messages()[-1].content == "你好"


async def test_provider_failure_does_not_commit():
    error = ProviderError("authentication", "鉴权失败")
    conversation = Conversation()
    session = ChatSession(FakeProvider(error=error), conversation, "系统", ToolRegistry())
    events = [event async for event in session.stream_turn("失败")]
    assert events[0].error is error
    assert conversation.get_messages() == []


async def test_multiple_tools_continue_after_failure_and_follow_up():
    records = []
    call1 = ToolCall("1", "Demo", {})
    call2 = ToolCall("2", "Broken", {})
    provider = SequenceProvider(
        [
            completed(calls=[call1, call2]),
            [ProviderEvent("text_delta", text="最终"), *completed("最终")],
        ]
    )
    registry = registry_with(
        RecordingTool(records),
        RecordingTool(records, name="Broken", fail=True),
    )
    session = ChatSession(provider, Conversation(), "系统", registry)
    events = [event async for event in session.stream_turn("执行")]
    results = [event.tool_result for event in events if event.type == "tool_result"]
    assert len(results) == 2
    assert [item.success for item in results] == [True, False]
    assert provider.requests[1][-1].role == "tool"
    assert events[-1].type == "completed"


async def test_followup_tool_call_hits_limit_without_execution():
    records = []
    first = ToolCall("1", "Demo", {})
    second = ToolCall("2", "Demo", {})
    provider = SequenceProvider([completed(calls=[first]), completed(calls=[second])])
    conversation = Conversation()
    session = ChatSession(
        provider,
        conversation,
        "系统",
        registry_with(RecordingTool(records)),
    )
    events = [event async for event in session.stream_turn("连续工具")]
    assert records == ["1"]
    assert events[-1].type == "limit"
    assert conversation.get_messages()[-1].content == LIMIT_MESSAGE
