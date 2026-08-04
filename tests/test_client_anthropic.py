"""Anthropic Client 的工具请求与流式解析测试。"""

from types import SimpleNamespace

import pytest

import dragon_code.clients.anthropic as anthropic_module
from dragon_code.clients.anthropic import AnthropicClient
from dragon_code.models import (
    ChatMessage,
    LLMRequest,
    ProviderConfig,
    SystemPrompt,
    ToolCall,
    ToolDefinition,
    ToolResult,
)


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


async def collect(client, messages=None, reminder=None):
    request = LLMRequest(
        messages=messages or [ChatMessage("user", "读取")],
        tools=[definition()],
        system=SystemPrompt("稳定系统提示", "动态环境信息"),
        reminder=reminder,
    )
    return [event async for event in client.stream(request)]


async def test_anthropic_request_contains_tool_result_and_hidden_block():
    FakeClient.events = []
    client = AnthropicClient(ProviderConfig("Claude", "anthropic", "key", "model"))
    call = ToolCall("u1", "Read", {"path": "a.txt"})
    result = ToolResult("u1", "Read", False, error_code="not_found", error_message="不存在")
    hidden = {"type": "thinking", "thinking": "", "signature": "signed"}
    await collect(
        client,
        [
            ChatMessage("user", "读取"),
            ChatMessage("assistant", tool_calls=[call], hidden_blocks=[hidden]),
            ChatMessage("tool", tool_results=[result]),
        ],
    )
    request = FakeClient.instances[0].messages.request
    assert request["tools"][0]["input_schema"] == {"type": "object"}
    assert len(request["system"]) == 2
    assert request["system"][0] == {
        "type": "text",
        "text": "稳定系统提示",
        "cache_control": {"type": "ephemeral"},
    }
    assert request["system"][1] == {"type": "text", "text": "动态环境信息"}
    assert "cache_control" not in request["tools"][0]
    assert request["messages"][1]["content"][0] == hidden
    assert request["messages"][2]["content"][0]["is_error"] is True


async def test_anthropic_reminder_is_temporary_and_follows_tool_results():
    call = ToolCall("u1", "Read", {"path": "a.txt"})
    tool_result = ToolResult("u1", "Read", True, content="内容")
    messages = [
        ChatMessage("user", "读取"),
        ChatMessage("assistant", tool_calls=[call]),
        ChatMessage("tool", tool_results=[tool_result]),
    ]

    await collect(
        client=AnthropicClient(ProviderConfig("Claude", "anthropic", "key", "model")),
        messages=messages,
        reminder="<system-reminder>只读</system-reminder>",
    )

    request = FakeClient.instances[0].messages.request
    final_content = request["messages"][-1]["content"]
    assert final_content[0]["type"] == "tool_result"
    assert final_content[-1] == {
        "type": "text",
        "text": "<system-reminder>只读</system-reminder>",
    }
    assert messages[-1].tool_results == [tool_result]
    assert messages[-1].content == ""


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
    events = await collect(AnthropicClient(ProviderConfig("Claude", "anthropic", "key", "model")))
    assert all("不能显示" not in event.text for event in events)
    call = next(event.tool_call for event in events if event.type == "tool_call")
    assert call.arguments == {"path": "a.txt"}
    assert events[-1].message.hidden_blocks[0]["signature"] == "signed"


async def test_anthropic_accepts_real_sdk_input_json_without_index():
    """真实 SDK 同时给出原始 delta 和不带 index 的高级事件。"""

    tool_start = SimpleNamespace(type="tool_use", id="u1", name="Read", input={})
    tool_stop = SimpleNamespace(type="tool_use", id="u1", name="Read", input={"path": "a.txt"})
    FakeClient.events = [
        SimpleNamespace(type="content_block_start", index=1, content_block=tool_start),
        SimpleNamespace(
            type="content_block_delta",
            index=1,
            delta=SimpleNamespace(
                type="input_json_delta",
                partial_json='{"path":"a.txt"}',
            ),
        ),
        SimpleNamespace(
            type="input_json",
            partial_json='{"path":"a.txt"}',
            snapshot='{"path":"a.txt"}',
        ),
        SimpleNamespace(type="content_block_stop", index=1, content_block=tool_stop),
    ]

    events = await collect(AnthropicClient(ProviderConfig("DeepSeek", "anthropic", "key", "model")))

    call = next(event.tool_call for event in events if event.type == "tool_call")
    assert call.arguments == {"path": "a.txt"}


async def test_anthropic_text_becomes_events():
    FakeClient.events = [
        SimpleNamespace(type="text", text="你"),
        SimpleNamespace(type="text", text="好"),
    ]
    events = await collect(AnthropicClient(ProviderConfig("Claude", "anthropic", "key", "model")))
    assert [event.text for event in events if event.type == "text_delta"] == ["你", "好"]
    assert events[-1].message.content == "你好"


async def test_anthropic_emits_stream_usage():
    FakeClient.events = [
        SimpleNamespace(
            type="message_start",
            message=SimpleNamespace(
                usage=SimpleNamespace(
                    input_tokens=12,
                    cache_creation_input_tokens=30,
                    cache_read_input_tokens=20,
                )
            ),
        ),
        SimpleNamespace(
            type="message_delta",
            usage=SimpleNamespace(output_tokens=5),
        ),
    ]
    events = await collect(AnthropicClient(ProviderConfig("Claude", "anthropic", "key", "model")))

    usage_event = next(event for event in events if event.type == "usage")
    assert usage_event.usage.input_tokens == 12
    assert usage_event.usage.output_tokens == 5
    assert usage_event.usage.cache_write_tokens == 30
    assert usage_event.usage.cache_read_tokens == 20


async def test_anthropic_allows_missing_usage():
    events = await collect(AnthropicClient(ProviderConfig("Claude", "anthropic", "key", "model")))

    usage_event = next(event for event in events if event.type == "usage")
    assert usage_event.usage.input_tokens is None
    assert usage_event.usage.output_tokens is None
    assert usage_event.usage.cache_write_tokens == 0
    assert usage_event.usage.cache_read_tokens == 0
