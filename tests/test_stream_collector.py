"""单轮流式收集器测试。"""

import pytest

from dragon_code.clients.base import LLMError
from dragon_code.models import ChatMessage, LLMEvent, TokenUsage
from dragon_code.stream_collector import StreamCollector


def test_collector_forwards_text_and_collects_message_and_usage():
    collector = StreamCollector()
    text_event = collector.accept(LLMEvent("text_delta", text="你好"))
    message = ChatMessage("assistant", "你好")

    collector.accept(LLMEvent("usage", usage=TokenUsage(10, 2, 30, 20)))
    collector.accept(LLMEvent("completed", message=message))
    response = collector.finish()

    assert text_event is not None
    assert text_event.type == "text"
    assert text_event.text == "你好"
    assert response.message is message
    assert response.usage == TokenUsage(10, 2, 30, 20)


def test_token_usage_adds_cache_usage_and_keeps_unknown_tokens():
    usage = TokenUsage(10, 2, 30, 20).add(TokenUsage(5, 3, 4, 6))

    assert usage == TokenUsage(15, 5, 34, 26)
    assert TokenUsage().add(TokenUsage(5, 3, 4, 6)) == TokenUsage(None, None, 4, 6)


def test_collector_rejects_incomplete_stream():
    collector = StreamCollector()
    collector.accept(LLMEvent("text_delta", text="未完成"))

    with pytest.raises(LLMError) as error:
        collector.finish()

    assert error.value.category == "invalid_response"
