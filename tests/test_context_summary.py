"""结构化摘要纯函数测试。"""

import pytest

from dragon_code.context.summary import (
    COMPACT_BOUNDARY,
    SUMMARY_SYSTEM_PROMPT,
    build_compacted_history,
    build_summary_user_prompt,
    extract_summary,
    select_recent_messages,
    serialize_messages,
)
from dragon_code.models import ChatMessage, ToolCall, ToolResult

VALID_SUMMARY = """1. 主要请求和意图：测试
2. 关键技术概念：测试
3. 文件和代码段：无
4. 错误与修复：无
5. 问题解决过程：无
6. 用户消息原文：原文
7. 待办任务：无
8. 当前工作和停止位置：测试
9. 可能的下一步：测试"""


def test_summary_prompt_has_nine_sections_and_forbids_tools_at_both_ends():
    history = [ChatMessage("user", "请保留我的原话")]

    prompt = build_summary_user_prompt(history)

    assert SUMMARY_SYSTEM_PROMPT.count("严禁调用任何工具") >= 2
    for index in range(1, 10):
        assert f"{index}." in SUMMARY_SYSTEM_PROMPT
    assert prompt.startswith("请压缩")
    assert prompt.endswith("严禁调用任何工具。")
    assert "请保留我的原话" in prompt


def test_serialize_messages_is_stable_and_keeps_protocol_data():
    messages = [
        ChatMessage(
            "assistant",
            "准备读取",
            tool_calls=[ToolCall("c1", "Read", {"path": "README.md"})],
        ),
        ChatMessage(
            "tool",
            tool_results=[ToolResult("c1", "Read", True, "内容")],
        ),
    ]

    first = serialize_messages(messages)

    assert first == serialize_messages(messages)
    assert '"call_id": "c1"' in first
    assert '"tool_name": "Read"' in first


def test_extract_summary_discards_analysis_and_requires_one_nonempty_block():
    response = f"<analysis>临时草稿</analysis><summary>{VALID_SUMMARY}</summary>"

    assert extract_summary(response) == VALID_SUMMARY

    for invalid in [
        "没有标签",
        "<summary>  </summary>",
        "<summary>一</summary><summary>二</summary>",
        "<summary>未闭合",
        "<summary>只有普通摘要，没有固定部分</summary>",
    ]:
        with pytest.raises(ValueError):
            extract_summary(invalid)


def test_recent_messages_satisfy_both_lower_bounds():
    messages = [ChatMessage("user", f"消息{index}-" + "x" * 100) for index in range(8)]

    recent = select_recent_messages(messages, min_tokens=1, min_messages=5)

    assert [message.content for message in recent] == [message.content for message in messages[-5:]]


def test_recent_messages_continue_until_token_lower_bound_is_met():
    messages = [ChatMessage("user", f"消息{index}-" + "x" * 4000) for index in range(6)]

    recent = select_recent_messages(messages, min_tokens=2000, min_messages=1)

    assert len(recent) == 2


def test_recent_boundary_never_splits_tool_call_and_result():
    messages = [
        ChatMessage("user", "旧消息"),
        ChatMessage(
            "assistant",
            tool_calls=[ToolCall("c1", "Read", {"path": "a.py"})],
        ),
        ChatMessage("tool", tool_results=[ToolResult("c1", "Read", True, "结果")]),
        ChatMessage("assistant", "完成"),
    ]

    recent = select_recent_messages(messages, min_tokens=1, min_messages=3)

    assert [message.role for message in recent] == ["assistant", "tool", "assistant"]


def test_recent_selection_returns_all_when_history_is_too_short():
    messages = [ChatMessage("user", "问题"), ChatMessage("assistant", "回答")]

    recent = select_recent_messages(messages)

    assert recent == messages
    assert recent is not messages


def test_compacted_history_adds_boundary_and_copies_recent_messages():
    recent = [ChatMessage("user", "原始用户消息")]

    compacted = build_compacted_history("九部分摘要", recent)
    recent[0].content = "被外部修改"

    assert compacted[0].role == "user"
    assert "<summary>" in compacted[0].content
    assert COMPACT_BOUNDARY in compacted[0].content
    assert compacted[1].content == "原始用户消息"
