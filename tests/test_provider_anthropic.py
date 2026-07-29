"""Anthropic Provider 的请求和流式解析测试。"""

from types import SimpleNamespace

import pytest

import dragon_code.providers.anthropic as anthropic_module
from dragon_code.models import ChatMessage, ProviderConfig
from dragon_code.providers.anthropic import AnthropicProvider
from dragon_code.providers.base import ProviderError


class FakeAnthropicStream:
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
            if isinstance(event, Exception):
                raise event
            yield event


class FakeMessages:
    def __init__(self, events):
        self.events = events
        self.request = None

    def stream(self, **request):
        self.request = request
        return FakeAnthropicStream(self.events)


class FakeAnthropicClient:
    instances = []
    events = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.messages = FakeMessages(list(self.events))
        self.instances.append(self)


@pytest.fixture(autouse=True)
def fake_anthropic(monkeypatch):
    FakeAnthropicClient.instances.clear()
    FakeAnthropicClient.events = []
    monkeypatch.setattr(anthropic_module, "AsyncAnthropic", FakeAnthropicClient)


async def collect(provider):
    return [
        text
        async for text in provider.stream(
            [ChatMessage("user", "你好")],
            "系统提示",
        )
    ]


async def test_anthropic_request_and_text_stream():
    FakeAnthropicClient.events = [
        SimpleNamespace(type="thinking", thinking="隐藏思考"),
        SimpleNamespace(type="text", text="你"),
        SimpleNamespace(type="text", text="好"),
        SimpleNamespace(type="message_stop"),
    ]
    config = ProviderConfig(
        "Claude",
        "anthropic",
        "secret",
        "claude-test",
        base_url="https://example.test",
        thinking=True,
    )
    provider = AnthropicProvider(config)

    chunks = await collect(provider)
    client = FakeAnthropicClient.instances[0]
    request = client.messages.request

    assert chunks == ["你", "好"]
    assert client.kwargs["base_url"] == "https://example.test"
    assert request["system"] == "系统提示"
    assert request["messages"] == [{"role": "user", "content": "你好"}]
    assert request["thinking"]["budget_tokens"] < request["max_tokens"]


async def test_anthropic_without_thinking_does_not_send_parameter():
    provider = AnthropicProvider(ProviderConfig("Claude", "anthropic", "key", "model"))

    await collect(provider)

    request = FakeAnthropicClient.instances[0].messages.request
    assert "thinking" not in request


async def test_anthropic_error_is_converted():
    FakeAnthropicClient.events = [ConnectionError("secret network detail")]
    provider = AnthropicProvider(ProviderConfig("Claude", "anthropic", "key", "model"))

    with pytest.raises(ProviderError, match="无法连接模型服务"):
        await collect(provider)
