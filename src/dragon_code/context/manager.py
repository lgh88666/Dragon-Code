"""上下文管理的 Agent 入口。"""

from __future__ import annotations

import asyncio
import copy
import json
import math
import os
import uuid
from dataclasses import asdict, replace
from pathlib import Path
from typing import TYPE_CHECKING

from dragon_code.context.constants import (
    AUTO_SAFETY_MARGIN,
    CHARS_PER_TOKEN,
    MANUAL_SAFETY_MARGIN,
    PREVIEW_MAX_BYTES,
    PREVIEW_MAX_LINES,
    SINGLE_TOOL_RESULT_BYTES,
    SUMMARY_OUTPUT_RESERVE,
    TOOL_RESULTS_MESSAGE_BYTES,
)
from dragon_code.context.state import (
    CompactCircuitBreaker,
    CompactOutcome,
    CompactStats,
    PrepareResult,
    ReplacementDecision,
    ReplacementLedger,
    SessionPaths,
    UsageAnchor,
)
from dragon_code.context.summary import (
    SUMMARY_SYSTEM_PROMPT,
    build_compacted_history,
    build_summary_user_prompt,
    extract_summary,
    select_recent_messages,
    serialize_messages,
)
from dragon_code.models import (
    ChatMessage,
    LLMRequest,
    SystemPrompt,
    TokenUsage,
    ToolDefinition,
    ToolResult,
)
from dragon_code.stream_collector import StreamCollector

if TYPE_CHECKING:
    from dragon_code.clients.base import LLMClient


def utf8_size(text: str) -> int:
    """返回文本的 UTF-8 字节数。"""

    return len(text.encode("utf-8"))


def preview_head(text: str) -> str:
    """返回同时满足行数和 UTF-8 字节限制的合法文本头部。"""

    line_limited = "".join(text.splitlines(keepends=True)[:PREVIEW_MAX_LINES])
    encoded = line_limited.encode("utf-8")
    if len(encoded) <= PREVIEW_MAX_BYTES:
        return line_limited
    return encoded[:PREVIEW_MAX_BYTES].decode("utf-8", errors="ignore")


class ContextManager:
    """协调工具结果落盘、Token 估算和历史压缩。"""

    def __init__(
        self,
        working_dir: Path,
        *,
        session_id: str | None = None,
        summary_client: LLMClient | None = None,
        context_window: int = 128_000,
    ):
        self.paths = SessionPaths.create(working_dir, session_id)
        self.summary_client = summary_client
        self.context_window = context_window
        self.ledger = ReplacementLedger()
        self.usage_anchor = UsageAnchor()
        self.circuit_breaker = CompactCircuitBreaker()
        self.offloaded_results = 0
        self.last_offload_failures = 0
        self.active_summary_task: asyncio.Task | None = None

    async def process_tool_results(self, results: list[ToolResult]) -> list[ToolResult]:
        """统一处理一轮结果，并保持模型原始调用顺序。"""

        self.last_offload_failures = 0
        processed = [replace(result, metadata=dict(result.metadata)) for result in results]
        sizes = [utf8_size(result.content) for result in results]
        replaced_indexes: set[int] = set()
        failed_indexes: set[int] = set()
        undecided_indexes: set[int] = set()

        for index, result in enumerate(results):
            decision = self.ledger.get(result.call_id)
            if decision is None:
                undecided_indexes.add(index)
                continue
            if decision.replaced:
                processed[index] = self._apply_decision(processed[index], decision)
                replaced_indexes.add(index)

        # 第一层：单个工具结果超过阈值时必须优先落盘。
        for index in sorted(undecided_indexes):
            if sizes[index] <= SINGLE_TOOL_RESULT_BYTES:
                continue
            decision = await self._try_offload(results[index], sizes[index])
            if decision is None:
                failed_indexes.add(index)
                continue
            self.ledger.freeze(results[index].call_id, decision)
            processed[index] = self._apply_decision(processed[index], decision)
            replaced_indexes.add(index)

        # 第二层：仅统计尚未被替换的原始内容，按大小稳定选择最少结果。
        remaining_bytes = sum(
            size for index, size in enumerate(sizes) if index not in replaced_indexes
        )
        aggregate_candidates = sorted(
            (
                index
                for index in undecided_indexes
                if index not in replaced_indexes and index not in failed_indexes
            ),
            key=lambda index: (-sizes[index], index),
        )
        for index in aggregate_candidates:
            if remaining_bytes <= TOOL_RESULTS_MESSAGE_BYTES:
                break
            decision = await self._try_offload(results[index], sizes[index])
            if decision is None:
                failed_indexes.add(index)
                continue
            self.ledger.freeze(results[index].call_id, decision)
            processed[index] = self._apply_decision(processed[index], decision)
            replaced_indexes.add(index)
            remaining_bytes -= sizes[index]

        # 只有成功完成处理的结果才冻结；落盘失败允许下一轮重试。
        for index in undecided_indexes - replaced_indexes - failed_indexes:
            self.ledger.freeze(
                results[index].call_id,
                ReplacementDecision(replaced=False, original_bytes=sizes[index]),
            )

        return processed

    @staticmethod
    def request_char_count(request: LLMRequest) -> int:
        """稳定统计一次完整协议无关请求的字符量。"""

        system_chars = len(json.dumps(asdict(request.system), ensure_ascii=False, sort_keys=True))
        message_chars = sum(len(serialize_messages([message])) for message in request.messages)
        tool_chars = sum(
            len(json.dumps(asdict(tool), ensure_ascii=False, sort_keys=True, default=str))
            for tool in request.tools
        )
        return system_chars + message_chars + tool_chars + len(request.reminder or "")

    def estimate_request_tokens(self, request: LLMRequest) -> int:
        """使用主请求 usage 锚点和字符增量估算当前请求。"""

        current_chars = self.request_char_count(request)
        if self.usage_anchor.valid:
            if current_chars >= self.usage_anchor.covered_chars:
                delta = current_chars - self.usage_anchor.covered_chars
                return self.usage_anchor.total_tokens + math.ceil(delta / CHARS_PER_TOKEN)
            self.usage_anchor.invalidate()
        return math.ceil(current_chars / CHARS_PER_TOKEN)

    def auto_compact_status(self, request: LLMRequest) -> tuple[bool, int, bool]:
        """返回是否会自动压缩、当前估算和熔断状态。"""

        estimated = self.estimate_request_tokens(request)
        threshold = self.context_window - SUMMARY_OUTPUT_RESERVE - AUTO_SAFETY_MARGIN
        return (
            estimated >= threshold and not self.circuit_breaker.tripped,
            estimated,
            (self.circuit_breaker.tripped),
        )

    def record_main_usage(
        self,
        request: LLMRequest,
        response_message: ChatMessage,
        usage: TokenUsage,
    ) -> None:
        """用最近一次主请求的真实 usage 替换旧锚点。"""

        total_tokens = usage.total_tokens
        if total_tokens is None:
            self.usage_anchor.invalidate()
            return
        covered_chars = self.request_char_count(request) + len(
            serialize_messages([response_message])
        )
        self.usage_anchor.update(total_tokens, covered_chars)

    async def prepare_request(
        self,
        committed_history: list[ChatMessage],
        pending_messages: list[ChatMessage],
        system: SystemPrompt,
        tools: list[ToolDefinition],
        reminder: str | None = None,
    ) -> PrepareResult:
        """在普通请求前估算窗口，并按需执行自动摘要。"""

        committed = copy.deepcopy(committed_history)
        pending = copy.deepcopy(pending_messages)
        request = LLMRequest(
            messages=[*committed, *pending],
            tools=list(tools),
            system=system,
            reminder=reminder,
        )
        before_tokens = self.estimate_request_tokens(request)
        threshold = self.context_window - SUMMARY_OUTPUT_RESERVE - AUTO_SAFETY_MARGIN
        if before_tokens < threshold:
            return PrepareResult(committed, request.messages)
        if self.circuit_breaker.tripped:
            return PrepareResult(committed, request.messages, circuit_tripped=True)

        outcome = await self._compact_history(
            committed,
            reason="auto",
            before_tokens=before_tokens,
            safety_margin=AUTO_SAFETY_MARGIN,
        )
        if not outcome.success:
            self.circuit_breaker.record_failure()
            return PrepareResult(
                committed,
                request.messages,
                compact=outcome,
                circuit_tripped=self.circuit_breaker.tripped,
            )

        self.circuit_breaker.record_success()
        self.usage_anchor.invalidate()
        messages = [*copy.deepcopy(outcome.history), *pending]
        compacted_request = LLMRequest(messages, list(tools), system, reminder)
        outcome.stats = replace(
            outcome.stats,
            after_tokens=self.estimate_request_tokens(compacted_request),
        )
        return PrepareResult(outcome.history, messages, compact=outcome)

    async def force_compact(
        self,
        committed_history: list[ChatMessage],
    ) -> CompactOutcome:
        """跳过自动阈值和熔断，手动尝试一次摘要。"""

        before_tokens = math.ceil(len(serialize_messages(committed_history)) / CHARS_PER_TOKEN)
        outcome = await self._compact_history(
            copy.deepcopy(committed_history),
            reason="manual",
            before_tokens=before_tokens,
            safety_margin=MANUAL_SAFETY_MARGIN,
        )
        if outcome.success:
            self.usage_anchor.invalidate()
        return outcome

    def restored_history_needs_compaction(
        self,
        history: list[ChatMessage],
        system: SystemPrompt,
        tools: list[ToolDefinition],
    ) -> bool:
        """判断恢复历史是否已经达到自动压缩阈值。"""

        request = LLMRequest(
            messages=copy.deepcopy(history),
            tools=list(tools),
            system=system,
        )
        should_compact, _estimated, _tripped = self.auto_compact_status(request)
        return should_compact

    async def compact_restored_history(
        self,
        history: list[ChatMessage],
    ) -> CompactOutcome:
        """恢复阶段只尝试一次压缩，不累计自动熔断次数。"""

        before_tokens = math.ceil(len(serialize_messages(history)) / CHARS_PER_TOKEN)
        outcome = await self._compact_history(
            copy.deepcopy(history),
            reason="restore",
            before_tokens=before_tokens,
            safety_margin=AUTO_SAFETY_MARGIN,
        )
        if outcome.success:
            self.usage_anchor.invalidate()
        return outcome

    def cancel_active(self) -> None:
        """取消当前摘要网络等待。"""

        if self.active_summary_task is not None and not self.active_summary_task.done():
            self.active_summary_task.cancel()

    async def _compact_history(
        self,
        history: list[ChatMessage],
        *,
        reason: str,
        before_tokens: int,
        safety_margin: int,
    ) -> CompactOutcome:
        if not history:
            return self._compact_failure(history, reason, before_tokens, "没有可压缩的历史。")
        if self.summary_client is None:
            return self._compact_failure(history, reason, before_tokens, "摘要模型不可用。")

        summary_request = LLMRequest(
            messages=[ChatMessage("user", build_summary_user_prompt(history))],
            tools=[],
            system=SystemPrompt(stable=SUMMARY_SYSTEM_PROMPT, environment=""),
        )
        summary_tokens = math.ceil(self.request_char_count(summary_request) / CHARS_PER_TOKEN)
        request_limit = self.context_window - SUMMARY_OUTPUT_RESERVE - safety_margin
        if summary_tokens > request_limit:
            return self._compact_failure(
                history,
                reason,
                before_tokens,
                "摘要输入超过当前模型的安全窗口。",
            )

        try:
            response = await self._collect_summary(summary_request)
            if response.tool_calls:
                raise ValueError("摘要模型返回了工具调用")
            summary = extract_summary(response.content)
            recent = select_recent_messages(history)
            compacted = build_compacted_history(summary, recent)
        except asyncio.CancelledError:
            raise
        except Exception:
            return self._compact_failure(
                history,
                reason,
                before_tokens,
                "摘要模型返回无效结果。",
            )

        after_tokens = math.ceil(len(serialize_messages(compacted)) / CHARS_PER_TOKEN)
        return CompactOutcome(
            True,
            compacted,
            CompactStats(
                reason=reason,
                before_tokens=before_tokens,
                after_tokens=after_tokens,
                offloaded_results=self.offloaded_results,
            ),
        )

    async def _collect_summary(self, request: LLMRequest) -> ChatMessage:
        collector = StreamCollector()
        stream = self.summary_client.stream(request)
        iterator = stream.__aiter__()
        try:
            while True:
                self.active_summary_task = asyncio.create_task(anext(iterator))
                try:
                    event = await self.active_summary_task
                except StopAsyncIteration:
                    break
                finally:
                    self.active_summary_task = None
                collector.accept(event)
        finally:
            self.active_summary_task = None
        return collector.finish().message

    @staticmethod
    def _compact_failure(
        history: list[ChatMessage],
        reason: str,
        before_tokens: int,
        message: str,
    ) -> CompactOutcome:
        return CompactOutcome(
            False,
            copy.deepcopy(history),
            CompactStats(reason=reason, before_tokens=before_tokens, error=message),
        )

    async def _try_offload(
        self,
        result: ToolResult,
        original_bytes: int,
    ) -> ReplacementDecision | None:
        final_path = self.paths.result_path(result.call_id)
        try:
            await asyncio.to_thread(self._write_result_sync, final_path, result.content)
        except OSError:
            self.last_offload_failures += 1
            return None

        preview = self._build_tool_preview(result, final_path, original_bytes)
        self.offloaded_results += 1
        return ReplacementDecision(
            replaced=True,
            preview=preview,
            file_path=final_path,
            original_bytes=original_bytes,
        )

    def _write_result_sync(self, final_path: Path, content: str) -> None:
        """同目录临时写入后原子替换，磁盘内容保持原始 UTF-8 字节。"""

        final_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = final_path.with_name(f".{final_path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temp_path.write_bytes(content.encode("utf-8"))
            os.replace(temp_path, final_path)
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _build_tool_preview(
        self,
        result: ToolResult,
        final_path: Path,
        original_bytes: int,
    ) -> str:
        relative_path = final_path.relative_to(self.paths.working_dir).as_posix()
        head = preview_head(result.content)
        line_count = len(result.content.splitlines())
        return (
            "[工具结果已保存到磁盘]\n"
            f"原始 UTF-8 字节数：{original_bytes}\n"
            f"原始行数：{line_count}\n"
            f"工具调用 ID：{result.call_id}\n"
            f"完整结果路径：{relative_path}\n"
            f"内容预览（最多 {PREVIEW_MAX_LINES} 行 / {PREVIEW_MAX_BYTES} 字节）：\n"
            "---\n"
            f"{head}\n"
            "---\n"
            "如需完整细节，请使用 Read 工具按段重新读取，例如："
            f'{{"path":"{relative_path}","offset":1,"limit":200}}'
        )

    @staticmethod
    def _apply_decision(
        result: ToolResult,
        decision: ReplacementDecision,
    ) -> ToolResult:
        metadata = dict(result.metadata)
        metadata.update(
            {
                "context_offloaded": True,
                "original_bytes": decision.original_bytes,
                "result_path": str(decision.file_path) if decision.file_path else "",
            }
        )
        return replace(
            result,
            content=decision.preview,
            metadata=metadata,
            truncated=True,
        )
