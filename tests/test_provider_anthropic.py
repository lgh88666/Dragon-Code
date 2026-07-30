"""Anthropic Provider 的工具请求与流式解析测试。"""

from types import SimpleNamespace

import pytest

import dragon_code.providers.anthropic as anthropic_module
from dragon_code.models import ChatMessage, ProviderConfig, ToolCall, ToolDefinition, ToolResult
from dragon_code.providers.anthropic import AnthropicProvider


class FakeStream:
    def __init__(self, events):
        self.events = events

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for event in self.events:
            yield event


class FakeMessages:
    def __init__(self, events):
        self.events = events
        self.request = None

    def stream(self, **request):
        self.request = request
        return FakeStream(self.events)


class FakeClient:
    instances = []
    events = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.messages = FakeMessages(list(self.events))
        self.instances.append(self)


@pytest.fixture(autouse=True)
def fake_client(monkeypatch):
    FakeClient.instances.clear()
    FakeClient.events = []
    monkeypatch.setattr(anthropic_module, "AsyncAnthropic", FakeClient)


def definition():
    return ToolDefinition("Read", "读取文件", {"type": "object"}, "filesystem", True, False, True)


async def collect(provider, messages=None):
    return [
        event
        async for event in provider.stream(
            messages or [ChatMessage("user", "读取")],
            "系统",
            [definition()],
        )
    ]


async def test_anthropic_request_contains_tool_result_and_hidden_block():
    FakeClient.events = []
    provider = AnthropicProvider(ProviderConfig("Claude", "anthropic", "key", "model"))
    call = ToolCall("u1", "Read", {"path": "a.txt"})
    result = ToolResult("u1", "Read", False, error_code="not_found", error_message="不存在")
    hidden = {"type": "thinking", "thinking": "", "signature": "signed"}
    await collect(
        provider,
        [
            ChatMessage("user", "读取"),
            ChatMessage("assistant", tool_calls=[call], hidden_blocks=[hidden]),
            ChatMessage("tool", tool_results=[result]),
        ],
    )
    request = FakeClient.instances[0].messages.request
    assert request["tools"][0]["input_schema"] == {"type": "object"}
    assert request["messages"][1]["content"][0] == hidden
    assert request["messages"][2]["content"][0]["is_error"] is True


async def test_anthropic_joins_tool_json_and_hides_thinking():
    tool_start = SimpleNamespace(type="tool_use", id="u1", name="Read", input={})
    tool_stop = SimpleNamespace(type="tool_use", id="u1", name="Read", input={"path": "a.txt"})
    thinking = SimpleNamespace(
        type="thinking",
        thinking="不能显示",
        signature="signed",
    )
    FakeClient.events = [
        SimpleNamespace(type="thinking", thinking="不能显示"),
        SimpleNamespace(type="content_block_stop", index=0, content_block=thinking),
        SimpleNamespace(type="content_block_start", index=1, content_block=tool_start),
        SimpleNamespace(type="input_json", index=1, partial_json='{"path":'),
        SimpleNamespace(type="input_json", index=1, partial_json='"a.txt"}'),
        SimpleNamespace(type="content_block_stop", index=1, content_block=tool_stop),
    ]
    events = await collect(AnthropicProvider(ProviderConfig("Claude", "anthropic", "key", "model")))
    assert all("不能显示" not in event.text for event in events)
    call = next(event.tool_call for event in events if event.type == "tool_call")
    assert call.arguments == {"path": "a.txt"}
    assert events[-1].message.hidden_blocks[0]["signature"] == "signed"


async def test_anthropic_text_becomes_events():
    FakeClient.events = [
        SimpleNamespace(type="text", text="你"),
        SimpleNamespace(type="text", text="好"),
    ]
    events = await collect(AnthropicProvider(ProviderConfig("Claude", "anthropic", "key", "model")))
    assert [event.text for event in events if event.type == "text_delta"] == ["你", "好"]
    assert events[-1].message.content == "你好"
