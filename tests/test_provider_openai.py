"""OpenAI Provider 的请求和流式解析测试。"""

from types import SimpleNamespace

import pytest

import dragon_code.providers.openai as openai_module
from dragon_code.models import ChatMessage, ProviderConfig
from dragon_code.providers.base import ProviderError
from dragon_code.providers.openai import OpenAIProvider


class FakeOpenAIStream:
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
        return FakeOpenAIStream(self.chunks)


class FakeOpenAIClient:
    instances = []
    chunks = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.chat = SimpleNamespace(completions=FakeCompletions(list(self.chunks)))
        self.instances.append(self)


@pytest.fixture(autouse=True)
def fake_openai(monkeypatch):
    FakeOpenAIClient.instances.clear()
    FakeOpenAIClient.chunks = []
    monkeypatch.setattr(openai_module, "AsyncOpenAI", FakeOpenAIClient)


def chunk(text):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=text))],
    )


async def collect(provider):
    messages = [
        ChatMessage("user", "第一轮"),
        ChatMessage("assistant", "第一答"),
        ChatMessage("user", "第二轮"),
    ]
    return [text async for text in provider.stream(messages, "系统提示")]


async def test_openai_request_and_text_stream():
    FakeOpenAIClient.chunks = [chunk("答"), chunk(None), chunk("案")]
    config = ProviderConfig(
        "OpenAI",
        "openai",
        "secret",
        "gpt-test",
        base_url="https://example.test/v1",
        thinking=True,
    )
    provider = OpenAIProvider(config)

    chunks = await collect(provider)
    client = FakeOpenAIClient.instances[0]
    request = client.chat.completions.request

    assert chunks == ["答", "案"]
    assert client.kwargs["base_url"] == "https://example.test/v1"
    assert request["messages"][0] == {"role": "system", "content": "系统提示"}
    assert [item["role"] for item in request["messages"][1:]] == [
        "user",
        "assistant",
        "user",
    ]
    assert "thinking" not in request


async def test_openai_ignores_chunks_without_choices():
    FakeOpenAIClient.chunks = [SimpleNamespace(choices=[]), chunk("正文")]
    provider = OpenAIProvider(ProviderConfig("OpenAI", "openai", "key", "model"))

    assert await collect(provider) == ["正文"]


async def test_openai_error_is_converted():
    FakeOpenAIClient.chunks = [ConnectionError("secret network detail")]
    provider = OpenAIProvider(ProviderConfig("OpenAI", "openai", "key", "model"))

    with pytest.raises(ProviderError, match="无法连接模型服务"):
        await collect(provider)
