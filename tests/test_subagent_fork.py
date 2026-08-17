from dragon_code.models import ChatMessage, ToolCall, ToolResult
from dragon_code.subagents.fork import build_fork_messages, is_fork_context


def test_fork_deep_copies_and_appends_task():
    parent = [
        ChatMessage(role="user", content="背景"),
        ChatMessage(role="assistant", content="收到"),
    ]

    forked = build_fork_messages(parent, None, "分析代码")
    forked[0].content = "已修改"

    assert parent[0].content == "背景"
    assert forked[-1].role == "user"
    assert "分析代码" in forked[-1].content
    assert is_fork_context(forked)
    assert not is_fork_context(parent)


def test_fork_adds_one_placeholder_for_each_pending_call():
    pending = ChatMessage(
        role="assistant",
        tool_calls=[
            ToolCall("call_1", "Read", {"path": "a.py"}),
            ToolCall("call_2", "Grep", {"pattern": "x"}),
        ],
    )

    forked = build_fork_messages([], pending, "继续")

    assert [message.role for message in forked] == ["assistant", "tool", "user"]
    assert [result.call_id for result in forked[1].tool_results] == ["call_1", "call_2"]
    assert all(result.error_code == "fork_placeholder" for result in forked[1].tool_results)


def test_fork_does_not_duplicate_existing_result():
    history = [
        ChatMessage(
            role="assistant",
            tool_calls=[
                ToolCall("call_1", "Read", {"path": "a.py"}),
                ToolCall("call_2", "Read", {"path": "b.py"}),
            ],
        ),
        ChatMessage(
            role="tool",
            tool_results=[ToolResult("call_1", "Read", True, content="ok")],
        ),
    ]

    forked = build_fork_messages(history, None, "继续")

    assert [result.call_id for result in forked[1].tool_results] == ["call_1", "call_2"]
