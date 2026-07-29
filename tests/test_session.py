"""Conversation 与 ChatSession 测试。"""

from conftest import FakeProvider

from dragon_code.models import ChatMessage
from dragon_code.providers.base import ProviderError
from dragon_code.session import ChatSession, Conversation


def test_conversation_returns_copy_and_commits_in_order():
    conversation = Conversation()
    request = conversation.build_request_messages("第一问")

    assert request == [ChatMessage("user", "第一问")]
    assert conversation.get_messages() == []

    conversation.commit_turn("第一问", "第一答")
    copied = conversation.get_messages()
    copied.clear()

    assert conversation.get_messages() == [
        ChatMessage("user", "第一问"),
        ChatMessage("assistant", "第一答"),
    ]


async def test_session_success_commits_history():
    provider = FakeProvider(chunks=["你", "好"])
    conversation = Conversation()
    session = ChatSession(provider, conversation, "系统提示")

    events = [event async for event in session.stream_turn("问候")]

    assert [event.type for event in events] == ["text", "text", "completed"]
    assert events[-1].text == "你好"
    assert conversation.get_messages() == [
        ChatMessage("user", "问候"),
        ChatMessage("assistant", "你好"),
    ]
    assert provider.received_system_prompt == "系统提示"


async def test_session_failure_does_not_commit_history():
    error = ProviderError("authentication", "鉴权失败")
    conversation = Conversation()
    session = ChatSession(FakeProvider(error=error), conversation, "系统提示")

    events = [event async for event in session.stream_turn("失败请求")]

    assert len(events) == 1
    assert events[0].type == "error"
    assert events[0].error is error
    assert conversation.get_messages() == []


async def test_second_turn_receives_first_turn_history():
    conversation = Conversation()
    first = FakeProvider(chunks=["第一答"])
    async for _event in ChatSession(first, conversation, "系统").stream_turn("第一问"):
        pass

    second = FakeProvider(chunks=["第二答"])
    async for _event in ChatSession(second, conversation, "系统").stream_turn("第二问"):
        pass

    assert second.received_messages == [
        ChatMessage("user", "第一问"),
        ChatMessage("assistant", "第一答"),
        ChatMessage("user", "第二问"),
    ]
