"""OpenAI Provider 的工具请求与流式解析测试。"""

from types import SimpleNamespace

import pytest

import dragon_code.providers.openai as openai_module
from dragon_code.models import ChatMessage, ProviderConfig, ToolCall, ToolDefinition, ToolResult
from dragon_code.providers.openai import OpenAIProvider


class FakeStream:
    def __init__(self, chunks):
        self.chunks = chunks

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for chunk in self.chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk


class FakeCompletions:
    def __init__(self, chunks):
        self.chunks = chunks
        self.request = None

    async def create(self, **request):
        self.request = request
        return FakeStream(self.chunks)


class FakeClient:
    instances = []
    chunks = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.chat = SimpleNamespace(completions=FakeCompletions(list(self.chunks)))
        self.instances.append(self)


@pytest.fixture(autouse=True)
def fake_client(monkeypatch):
    FakeClient.instances.clear()
    FakeClient.chunks = []
    monkeypatch.setattr(openai_module, "AsyncOpenAI", FakeClient)


def definition():
    return ToolDefinition("Read", "读取文件", {"type": "object"}, "filesystem", True, False, True)


def chunk(content=None, tool_calls=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def tool_part(index, call_id=None, name=None, arguments=None):
    function = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(index=index, id=call_id, function=function)


async def collect(provider, messages=None):
    return [
        event
        async for event in provider.stream(
            messages or [ChatMessage("user", "读取文件")],
            "系统提示",
            [definition()],
        )
    ]


async def test_openai_request_contains_tools_and_tool_history():
    FakeClient.chunks = [chunk("完成")]
    provider = OpenAIProvider(ProviderConfig("OpenAI", "openai", "key", "model"))
    call = ToolCall("call_1", "Read", {"path": "a.txt"}, '{"path":"a.txt"}')
    result = ToolResult("call_1", "Read", True, content="内容")
    messages = [
        ChatMessage("user", "读取"),
        ChatMessage("assistant", tool_calls=[call]),
        ChatMessage("tool", tool_results=[result]),
    ]
    await collect(provider, messages)
    request = FakeClient.instances[0].chat.completions.request
    assert request["tools"][0]["function"]["name"] == "Read"
    assert request["messages"][-1]["role"] == "tool"
    assert request["messages"][-1]["tool_call_id"] == "call_1"


async def test_openai_joins_multiple_fragmented_calls():
    FakeClient.chunks = [
        chunk(tool_calls=[tool_part(0, "call_1", "Re", '{"pa')]),
        chunk(tool_calls=[tool_part(1, "call_2", "Gl", '{"pat')]),
        chunk(tool_calls=[tool_part(0, None, "ad", 'th":"a.txt"}')]),
        chunk(tool_calls=[tool_part(1, None, "ob", 'tern":"*.py"}')]),
    ]
    events = await collect(OpenAIProvider(ProviderConfig("OpenAI", "openai", "key", "model")))
    calls = [event.tool_call for event in events if event.type == "tool_call"]
    assert [(call.name, call.arguments) for call in calls] == [
        ("Read", {"path": "a.txt"}),
        ("Glob", {"pattern": "*.py"}),
    ]
    assert events[-1].type == "completed"
    assert events[-1].message.tool_calls == calls


async def test_openai_text_and_invalid_json_events():
    FakeClient.chunks = [
        chunk("正在处理"),
        chunk(tool_calls=[tool_part(0, "x", "Read", "{")]),
    ]
    events = await collect(OpenAIProvider(ProviderConfig("OpenAI", "openai", "key", "model")))
    assert events[0].type == "text_delta"
    assert events[1].tool_call.arguments is None
    assert events[-1].message.content == "正在处理"
