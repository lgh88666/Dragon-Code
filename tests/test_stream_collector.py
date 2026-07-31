"""单轮流式收集器测试。"""

import pytest

from dragon_code.models import ChatMessage, ProviderEvent, TokenUsage
from dragon_code.providers.base import ProviderError
from dragon_code.stream_collector import StreamCollector


def test_collector_forwards_text_and_collects_message_and_usage():
    collector = StreamCollector()
    text_event = collector.accept(ProviderEvent("text_delta", text="你好"))
    message = ChatMessage("assistant", "你好")

    collector.accept(ProviderEvent("usage", usage=TokenUsage(10, 2)))
    collector.accept(ProviderEvent("completed", message=message))
    response = collector.finish()

    assert text_event is not None
    assert text_event.type == "text"
    assert text_event.text == "你好"
    assert response.message is message
    assert response.usage == TokenUsage(10, 2)


def test_collector_rejects_incomplete_stream():
    collector = StreamCollector()
    collector.accept(ProviderEvent("text_delta", text="未完成"))

    with pytest.raises(ProviderError) as error:
        collector.finish()

    assert error.value.category == "invalid_response"
