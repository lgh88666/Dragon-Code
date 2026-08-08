"""Conversation 对话历史测试。"""

from dragon_code.models import ChatMessage, ToolCall, ToolResult
from dragon_code.session import Conversation


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


def test_build_request_does_not_modify_history():
    conversation = Conversation()
    conversation.commit_messages([ChatMessage("assistant", "已有回答")])

    request = conversation.build_request_messages("新问题")

    assert [message.role for message in request] == ["assistant", "user"]
    assert [message.role for message in conversation.get_messages()] == ["assistant"]


def test_commit_messages_keeps_batch_order():
    conversation = Conversation()
    batch = [
        ChatMessage("user", "执行任务"),
        ChatMessage("assistant", tool_calls=[]),
        ChatMessage("tool", tool_results=[]),
        ChatMessage("assistant", "完成"),
    ]

    conversation.commit_messages(batch)

    assert conversation.get_messages() == batch


def test_replace_messages_deep_copies_nested_tool_data():
    conversation = Conversation()
    replacement = [
        ChatMessage(
            "assistant",
            tool_calls=[ToolCall("c1", "Read", {"path": "a.py"})],
        ),
        ChatMessage(
            "tool",
            tool_results=[ToolResult("c1", "Read", True, "原结果")],
        ),
    ]

    conversation.replace_messages(replacement)
    replacement[0].tool_calls[0].arguments["path"] = "changed.py"
    replacement[1].tool_results[0].content = "被修改"
    copied = conversation.get_messages()

    assert copied[0].tool_calls[0].arguments["path"] == "a.py"
    assert copied[1].tool_results[0].content == "原结果"

    copied[0].tool_calls.clear()
    assert len(conversation.get_messages()[0].tool_calls) == 1


def test_replace_messages_can_clear_history():
    conversation = Conversation()
    conversation.commit_messages([ChatMessage("user", "旧历史")])

    conversation.replace_messages([])

    assert conversation.get_messages() == []
