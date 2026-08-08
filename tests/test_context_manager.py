"""ContextManager 两层上下文管理测试。"""

import asyncio
import math
from pathlib import Path

import pytest

from dragon_code.context.constants import (
    CHARS_PER_TOKEN,
    PREVIEW_MAX_BYTES,
    PREVIEW_MAX_LINES,
)
from dragon_code.context.manager import ContextManager, preview_head, utf8_size
from dragon_code.context.summary import serialize_messages
from dragon_code.models import (
    ChatMessage,
    LLMEvent,
    LLMRequest,
    SystemPrompt,
    TokenUsage,
    ToolCall,
    ToolDefinition,
    ToolResult,
)

VALID_SUMMARY = """<analysis>草稿</analysis><summary>
1. 主要请求和意图：继续任务
2. 关键技术概念：上下文
3. 文件和代码段：无
4. 错误与修复：无
5. 问题解决过程：无
6. 用户消息原文：原话
7. 待办任务：继续
8. 当前工作和停止位置：测试
9. 可能的下一步：实现
</summary>"""


class FakeSummaryClient:
    model = "deepseek-v4-flash"

    def __init__(self, responses: list[ChatMessage] | None = None):
        self.responses = responses or [ChatMessage("assistant", VALID_SUMMARY)]
        self.requests: list[LLMRequest] = []

    async def stream(self, request: LLMRequest):
        self.requests.append(request)
        response = self.responses[min(len(self.requests) - 1, len(self.responses) - 1)]
        yield LLMEvent("usage", usage=TokenUsage(100, 20))
        yield LLMEvent("completed", message=response)


def large_tool_definition() -> ToolDefinition:
    return ToolDefinition(
        name="LargeTool",
        description="x" * 70_000,
        input_schema={"type": "object"},
        category="read",
        read_only=True,
        destructive=False,
        is_concurrency_safe=True,
    )


def make_result(call_id: str, content: str) -> ToolResult:
    return ToolResult(
        call_id=call_id,
        tool_name="Read",
        success=True,
        content=content,
        metadata={"source": "test"},
    )


def test_preview_head_obeys_lines_bytes_and_utf8_boundaries():
    text = "".join(f"第{index}行：" + "龙" * 200 + "\n" for index in range(30))

    head = preview_head(text)

    assert len(head.splitlines()) <= PREVIEW_MAX_LINES
    assert utf8_size(head) <= PREVIEW_MAX_BYTES
    head.encode("utf-8").decode("utf-8")


@pytest.mark.asyncio
async def test_single_large_result_is_offloaded_exactly(tmp_path: Path):
    manager = ContextManager(tmp_path, session_id="1234567890-deadbeef")
    content = "龙" * 16_667

    processed = await manager.process_tool_results([make_result("call/1", content)])

    result = processed[0]
    assert result.truncated is True
    assert result.metadata["context_offloaded"] is True
    assert "原始 UTF-8 字节数：50001" in result.content
    assert "使用 Read 工具按段重新读取" in result.content
    assert '"offset":1,"limit":200' in result.content
    saved_path = Path(result.metadata["result_path"])
    assert saved_path.read_bytes() == content.encode("utf-8")


@pytest.mark.asyncio
async def test_exact_single_limit_is_kept(tmp_path: Path):
    manager = ContextManager(tmp_path, session_id="1234567890-deadbeef")
    original = make_result("call-1", "a" * 50_000)

    processed = await manager.process_tool_results([original])

    assert processed[0].content == original.content
    assert processed[0].truncated is False
    assert manager.ledger.get("call-1").replaced is False


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [49_999, 50_000])
async def test_single_results_at_or_below_limit_are_kept(tmp_path: Path, size: int):
    manager = ContextManager(tmp_path, session_id="1234567890-deadbeef")

    processed = await manager.process_tool_results([make_result("call-1", "x" * size)])

    assert processed[0].truncated is False
    assert processed[0].content == "x" * size


@pytest.mark.asyncio
async def test_offload_returns_new_result_and_preserves_error_semantics(tmp_path: Path):
    manager = ContextManager(tmp_path, session_id="1234567890-deadbeef")
    original = ToolResult(
        "call-1",
        "Bash",
        False,
        "x" * 50_001,
        error_code="nonzero_exit",
        error_message="退出码为1",
        metadata={"exit_code": 1},
    )

    processed = (await manager.process_tool_results([original]))[0]

    assert processed is not original
    assert original.content == "x" * 50_001
    assert processed.call_id == original.call_id
    assert processed.tool_name == original.tool_name
    assert processed.success is False
    assert processed.error_code == original.error_code
    assert processed.error_message == original.error_message
    assert processed.metadata["exit_code"] == 1


@pytest.mark.asyncio
async def test_aggregate_five_equal_results_offloads_first_only(tmp_path: Path):
    manager = ContextManager(tmp_path, session_id="1234567890-deadbeef")
    originals = [make_result(f"call-{index}", str(index) * 45_000) for index in range(5)]

    processed = await manager.process_tool_results(originals)

    assert [result.truncated for result in processed] == [True, False, False, False, False]
    assert manager.offloaded_results == 1


@pytest.mark.asyncio
async def test_aggregate_exact_limit_keeps_every_result(tmp_path: Path):
    manager = ContextManager(tmp_path, session_id="1234567890-deadbeef")
    originals = [make_result(f"call-{index}", "x" * 40_000) for index in range(5)]

    processed = await manager.process_tool_results(originals)

    assert all(result.truncated is False for result in processed)


@pytest.mark.asyncio
async def test_single_rule_offload_is_not_counted_again_for_aggregate(tmp_path: Path):
    manager = ContextManager(tmp_path, session_id="1234567890-deadbeef")
    originals = [make_result("large", "x" * 60_000)]
    originals.extend(make_result(f"small-{index}", "x" * 40_000) for index in range(4))

    processed = await manager.process_tool_results(originals)

    assert [result.truncated for result in processed] == [True, False, False, False, False]


@pytest.mark.asyncio
async def test_frozen_keep_decision_does_not_flip_in_later_large_batch(tmp_path: Path):
    manager = ContextManager(tmp_path, session_id="1234567890-deadbeef")
    kept = make_result("kept", "k" * 45_000)
    await manager.process_tool_results([kept])
    batch = [kept, *[make_result(f"new-{index}", "x" * 45_000) for index in range(4)]]

    processed = await manager.process_tool_results(batch)

    assert processed[0].truncated is False
    assert sum(result.truncated for result in processed) == 1


@pytest.mark.asyncio
async def test_aggregate_uses_largest_result_then_keeps_order(tmp_path: Path):
    manager = ContextManager(tmp_path, session_id="1234567890-deadbeef")
    sizes = [45_000, 49_000, 46_000, 48_000, 47_000]
    originals = [make_result(f"call-{index}", "x" * size) for index, size in enumerate(sizes)]

    processed = await manager.process_tool_results(originals)

    assert [result.call_id for result in processed] == [f"call-{index}" for index in range(5)]
    assert [result.truncated for result in processed] == [False, True, False, False, False]


@pytest.mark.asyncio
async def test_repeated_processing_reuses_preview_without_rewriting(tmp_path: Path):
    manager = ContextManager(tmp_path, session_id="1234567890-deadbeef")
    original = make_result("call-1", "x" * 50_001)

    first = (await manager.process_tool_results([original]))[0]
    path = Path(first.metadata["result_path"])
    first_mtime = path.stat().st_mtime_ns
    second = (await manager.process_tool_results([original]))[0]

    assert second.content == first.content
    assert path.stat().st_mtime_ns == first_mtime
    assert manager.offloaded_results == 1


@pytest.mark.asyncio
async def test_write_failure_keeps_original_and_allows_retry(tmp_path: Path, monkeypatch):
    manager = ContextManager(tmp_path, session_id="1234567890-deadbeef")
    original = make_result("call-1", "x" * 50_001)
    real_write = manager._write_result_sync

    def fail_write(path: Path, content: str) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr(manager, "_write_result_sync", fail_write)
    failed = (await manager.process_tool_results([original]))[0]

    assert failed.content == original.content
    assert manager.ledger.get("call-1") is None
    assert manager.paths.result_path("call-1").exists() is False

    monkeypatch.setattr(manager, "_write_result_sync", real_write)
    retried = (await manager.process_tool_results([original]))[0]
    assert retried.truncated is True
    assert manager.ledger.get("call-1").replaced is True


def test_request_estimate_uses_latest_usage_anchor_and_positive_delta(tmp_path: Path):
    manager = ContextManager(tmp_path, session_id="1234567890-deadbeef")
    system = SystemPrompt("stable", "environment")
    first = LLMRequest([ChatMessage("user", "问题")], [], system)
    response = ChatMessage("assistant", "回答")

    assert manager.estimate_request_tokens(first) == math.ceil(
        manager.request_char_count(first) / CHARS_PER_TOKEN
    )

    manager.record_main_usage(first, response, TokenUsage(100, 20))
    tool_message = ChatMessage(
        "tool",
        tool_results=[ToolResult("call-1", "Read", True, "新增" * 100)],
    )
    second = LLMRequest([*first.messages, response, tool_message], [], system)
    expected_delta = len(serialize_messages([tool_message]))

    assert manager.estimate_request_tokens(second) == 120 + math.ceil(
        expected_delta / CHARS_PER_TOKEN
    )


def test_shortened_history_invalidates_usage_anchor(tmp_path: Path):
    manager = ContextManager(tmp_path, session_id="1234567890-deadbeef")
    system = SystemPrompt("stable", "environment")
    long_request = LLMRequest([ChatMessage("user", "x" * 1000)], [], system)
    manager.record_main_usage(
        long_request,
        ChatMessage("assistant", "y" * 100),
        TokenUsage(300, 20),
    )
    short_request = LLMRequest([ChatMessage("user", "短")], [], system)

    estimated = manager.estimate_request_tokens(short_request)

    assert manager.usage_anchor.valid is False
    assert estimated == math.ceil(manager.request_char_count(short_request) / CHARS_PER_TOKEN)


def test_unknown_main_usage_invalidates_anchor(tmp_path: Path):
    manager = ContextManager(tmp_path, session_id="1234567890-deadbeef")
    request = LLMRequest([], [], SystemPrompt("", ""))
    manager.usage_anchor.update(100, 100)

    manager.record_main_usage(request, ChatMessage("assistant", "ok"), TokenUsage())

    assert manager.usage_anchor.valid is False


def test_tool_schema_and_reminder_are_included_in_estimate(tmp_path: Path):
    manager = ContextManager(tmp_path, session_id="1234567890-deadbeef")
    system = SystemPrompt("stable", "environment")
    base = LLMRequest([ChatMessage("user", "问题")], [], system)
    expanded = LLMRequest(
        base.messages,
        [
            ToolDefinition(
                "Demo",
                "description",
                {"type": "object", "properties": {"value": {"description": "x" * 1000}}},
                "read",
                True,
                False,
                True,
            )
        ],
        system,
        reminder="r" * 1000,
    )

    assert manager.estimate_request_tokens(expanded) > manager.estimate_request_tokens(base)


def test_latest_main_usage_replaces_anchor_instead_of_accumulating(tmp_path: Path):
    manager = ContextManager(tmp_path, session_id="1234567890-deadbeef")
    request = LLMRequest([], [], SystemPrompt("", ""))
    response = ChatMessage("assistant", "ok")

    for total in [1000, 1500, 2200]:
        manager.record_main_usage(request, response, TokenUsage(total - 1, 1))
        assert manager.usage_anchor.total_tokens == total


def test_assistant_output_is_not_double_counted_after_anchor(tmp_path: Path):
    manager = ContextManager(tmp_path, session_id="1234567890-deadbeef")
    system = SystemPrompt("stable", "environment")
    request = LLMRequest([ChatMessage("user", "问题")], [], system)
    response = ChatMessage("assistant", "回答")
    manager.record_main_usage(request, response, TokenUsage(90, 10))

    next_request = LLMRequest([*request.messages, response], [], system)

    assert manager.estimate_request_tokens(next_request) == 100


@pytest.mark.asyncio
async def test_failed_summary_usage_does_not_replace_main_anchor(tmp_path: Path):
    client = FakeSummaryClient([ChatMessage("assistant", "无有效摘要")])
    manager = ContextManager(
        tmp_path,
        session_id="1234567890-deadbeef",
        summary_client=client,
    )
    manager.usage_anchor.update(777, 888)

    outcome = await manager.force_compact([ChatMessage("user", "历史")])

    assert outcome.success is False
    assert manager.usage_anchor.valid is True
    assert manager.usage_anchor.total_tokens == 777


@pytest.mark.asyncio
async def test_auto_threshold_minus_one_does_not_call_summary(tmp_path: Path, monkeypatch):
    client = FakeSummaryClient()
    manager = ContextManager(
        tmp_path,
        session_id="1234567890-deadbeef",
        summary_client=client,
        context_window=50_000,
    )
    monkeypatch.setattr(manager, "estimate_request_tokens", lambda request: 16_999)

    prepared = await manager.prepare_request(
        [ChatMessage("user", "历史")],
        [ChatMessage("user", "本轮")],
        SystemPrompt("s", "e"),
        [],
    )

    assert prepared.compact is None
    assert client.requests == []


@pytest.mark.asyncio
async def test_auto_compact_uses_empty_tools_and_keeps_pending_user_exact(tmp_path: Path):
    client = FakeSummaryClient()
    manager = ContextManager(
        tmp_path,
        session_id="1234567890-deadbeef",
        summary_client=client,
        context_window=50_000,
    )
    history = [ChatMessage("user", "较早消息"), ChatMessage("assistant", "较早回答")]
    pending = [ChatMessage("user", "本轮用户原文，不得改写")]

    prepared = await manager.prepare_request(
        history,
        pending,
        SystemPrompt("system", "environment"),
        [large_tool_definition()],
    )

    assert prepared.compact is not None and prepared.compact.success is True
    assert prepared.request_messages[-1].content == "本轮用户原文，不得改写"
    assert client.requests[0].tools == []
    assert "严禁调用任何工具" in client.requests[0].system.stable
    assert "<analysis>" not in prepared.committed_history[0].content
    assert manager.circuit_breaker.consecutive_failures == 0


@pytest.mark.asyncio
async def test_auto_compact_failure_continues_and_trips_after_three(tmp_path: Path):
    client = FakeSummaryClient([ChatMessage("assistant", "无有效摘要")])
    manager = ContextManager(
        tmp_path,
        session_id="1234567890-deadbeef",
        summary_client=client,
        context_window=50_000,
    )
    history = [ChatMessage("user", "原历史")]
    pending = [ChatMessage("user", "新问题")]
    kwargs = {
        "committed_history": history,
        "pending_messages": pending,
        "system": SystemPrompt("system", "environment"),
        "tools": [large_tool_definition()],
    }

    for _ in range(3):
        prepared = await manager.prepare_request(**kwargs)
        assert prepared.request_messages == [*history, *pending]
        assert prepared.compact is not None and prepared.compact.success is False

    assert manager.circuit_breaker.tripped is True
    assert prepared.circuit_tripped is True

    fourth = await manager.prepare_request(**kwargs)
    assert fourth.circuit_tripped is True
    assert len(client.requests) == 3


@pytest.mark.asyncio
async def test_auto_success_resets_previous_failures(tmp_path: Path):
    client = FakeSummaryClient(
        [
            ChatMessage("assistant", "无摘要"),
            ChatMessage("assistant", "还是无摘要"),
            ChatMessage("assistant", VALID_SUMMARY),
        ]
    )
    manager = ContextManager(
        tmp_path,
        session_id="1234567890-deadbeef",
        summary_client=client,
        context_window=50_000,
    )
    kwargs = {
        "committed_history": [ChatMessage("user", "历史")],
        "pending_messages": [ChatMessage("user", "本轮")],
        "system": SystemPrompt("s", "e"),
        "tools": [large_tool_definition()],
    }

    await manager.prepare_request(**kwargs)
    await manager.prepare_request(**kwargs)
    success = await manager.prepare_request(**kwargs)

    assert success.compact is not None and success.compact.success is True
    assert manager.circuit_breaker.consecutive_failures == 0


@pytest.mark.asyncio
async def test_manual_compact_bypasses_threshold_and_breaker(tmp_path: Path):
    client = FakeSummaryClient()
    manager = ContextManager(
        tmp_path,
        session_id="1234567890-deadbeef",
        summary_client=client,
        context_window=128_000,
    )
    for _ in range(3):
        manager.circuit_breaker.record_failure()

    outcome = await manager.force_compact([ChatMessage("user", "很短的历史")])

    assert outcome.success is True
    assert len(client.requests) == 1
    assert manager.circuit_breaker.consecutive_failures == 3


@pytest.mark.asyncio
async def test_manual_compact_rejects_unsafe_summary_input_without_history_change(
    tmp_path: Path,
):
    client = FakeSummaryClient()
    manager = ContextManager(
        tmp_path,
        session_id="1234567890-deadbeef",
        summary_client=client,
        context_window=23_001,
    )
    history = [ChatMessage("user", "历史")]

    outcome = await manager.force_compact(history)

    assert outcome.success is False
    assert outcome.history == history
    assert len(client.requests) == 0
    assert manager.circuit_breaker.consecutive_failures == 0


@pytest.mark.asyncio
async def test_summary_tool_call_is_rejected(tmp_path: Path):
    response = ChatMessage(
        "assistant",
        VALID_SUMMARY,
        tool_calls=[ToolCall("c1", "Read", {"path": "x"})],
    )
    manager = ContextManager(
        tmp_path,
        session_id="1234567890-deadbeef",
        summary_client=FakeSummaryClient([response]),
    )

    outcome = await manager.force_compact([ChatMessage("user", "历史")])

    assert outcome.success is False


@pytest.mark.asyncio
async def test_cancel_active_summary_propagates_cancellation(tmp_path: Path):
    started = asyncio.Event()

    class BlockingClient:
        async def stream(self, request: LLMRequest):
            started.set()
            await asyncio.Event().wait()
            yield LLMEvent("completed", message=ChatMessage("assistant", VALID_SUMMARY))

    manager = ContextManager(
        tmp_path,
        session_id="1234567890-deadbeef",
        summary_client=BlockingClient(),
    )
    task = asyncio.create_task(manager.force_compact([ChatMessage("user", "历史")]))
    await started.wait()

    manager.cancel_active()

    with pytest.raises(asyncio.CancelledError):
        await task
