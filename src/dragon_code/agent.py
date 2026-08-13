"""Dragon Code 的 ReAct Agent Loop。"""

from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from typing import TYPE_CHECKING

from dragon_code.clients.base import LLMClient, LLMError
from dragon_code.context.manager import ContextManager
from dragon_code.models import (
    AgentEvent,
    ChatMessage,
    CompactEvent,
    LLMRequest,
    TokenUsage,
    ToolCall,
    ToolResult,
)
from dragon_code.permissions import (
    ApprovalChoice,
    PermissionDecision,
    PermissionMode,
    PermissionRequest,
    PermissionResult,
)
from dragon_code.permissions.approval import ApprovalController
from dragon_code.permissions.engine import PermissionEngine
from dragon_code.permissions.rules import RuleParseError, RuleStore, make_exact_rule
from dragon_code.prompt import build_system_prompt, plan_reminder
from dragon_code.session import Conversation
from dragon_code.stream_collector import StreamCollector
from dragon_code.tool_scheduler import ToolBatch, ToolScheduler
from dragon_code.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from dragon_code.memory import MemoryManager

ITERATION_LIMIT_MESSAGE = "已达到 Agent Loop 的 50 次迭代上限。"
UNKNOWN_TOOL_LIMIT_MESSAGE = "模型连续请求未知工具，Agent Loop 已停止。"


class Agent:
    """连接模型、工具和历史，持续工作到任务完成。"""

    def __init__(
        self,
        client: LLMClient,
        conversation: Conversation,
        registry: ToolRegistry,
        working_dir: Path,
        version: str,
        max_iterations: int = 50,
        unknown_tool_limit: int = 3,
        permission_engine: PermissionEngine | None = None,
        approval_controller: ApprovalController | None = None,
        permission_mode: PermissionMode = PermissionMode.DEFAULT,
        context_manager: ContextManager | None = None,
        custom_instructions: str = "",
        memory_manager: MemoryManager | None = None,
    ):
        self.client = client
        self.conversation = conversation
        self.registry = registry
        self.working_dir = working_dir.resolve()
        self.version = version
        self.plan_registry = registry.subset({"Read", "Glob", "Grep"})
        self.max_iterations = max_iterations
        self.unknown_tool_limit = unknown_tool_limit
        self.context_manager = context_manager or ContextManager(self.working_dir)
        self.custom_instructions = custom_instructions
        self.memory_manager = memory_manager
        self.completed_turns = 0

        # 默认空规则只用于向后兼容和测试；TUI 启动时会注入真实三级配置。
        if permission_engine is None:
            empty_rules = RuleStore.empty(self.working_dir)
            permission_engine = PermissionEngine(self.working_dir, empty_rules)
        self.permission_engine = permission_engine
        self.approval_controller = approval_controller or ApprovalController()

        self.mode = permission_mode
        self.has_plan = False
        self.cancel_requested = False
        self.task_usage = TokenUsage(0, 0)
        self.active_client_task: asyncio.Task | None = None
        self.scheduler: ToolScheduler | None = None

    def enter_plan_mode(self) -> None:
        """进入持续计划模式；从 Default 进入时清空旧计划标记。"""

        self.set_permission_mode(PermissionMode.PLAN)

    def can_execute_plan(self) -> bool:
        return self.mode is PermissionMode.PLAN and self.has_plan

    def enter_default_mode(self) -> None:
        self.set_permission_mode(PermissionMode.DEFAULT)

    def set_permission_mode(self, mode: PermissionMode) -> None:
        """切换会话权限模式，并清理不再适用的旧计划。"""

        if mode is not self.mode:
            self.has_plan = False
        self.mode = mode

    def cycle_permission_mode(self) -> PermissionMode:
        """按固定顺序切换权限模式，供 Shift+Tab 使用。"""

        modes = list(PermissionMode)
        current_index = modes.index(self.mode)
        self.set_permission_mode(modes[(current_index + 1) % len(modes)])
        return self.mode

    def resolve_permission(self, call_id: str, choice: ApprovalChoice) -> None:
        """接收 TUI 对当前权限确认的回答。"""

        self.approval_controller.resolve(call_id, choice)

    def request_cancel(self) -> None:
        """停止当前网络等待或工具批次，外层循环负责合法收尾。"""

        self.cancel_requested = True
        if self.active_client_task is not None and not self.active_client_task.done():
            self.active_client_task.cancel()
        if self.scheduler is not None:
            self.scheduler.cancel_active()
        self.context_manager.cancel_active()
        self.approval_controller.cancel()

    async def compact_context(self):
        """手动压缩已提交历史，不发起普通对话请求。"""

        outcome = await self.context_manager.force_compact(self.conversation.get_messages())
        phase = "manual_complete" if outcome.success else "manual_failed"
        if outcome.success:
            self.conversation.replace_messages(outcome.history)
            warning = self.conversation.take_persistence_warning()
            if warning:
                yield AgentEvent(type="session_warning", text=warning)
        yield AgentEvent(
            type="compact",
            compact=CompactEvent(
                phase=phase,
                before_tokens=outcome.stats.before_tokens,
                after_tokens=outcome.stats.after_tokens,
                offloaded_results=outcome.stats.offloaded_results,
                message=outcome.stats.error,
            ),
        )

    async def run(self, user_text: str, *, read_only: bool = False):
        """运行一个完整任务，异步产出界面所需事件。"""

        self.cancel_requested = False
        self.task_usage = TokenUsage(0, 0)
        planning = self.mode is PermissionMode.PLAN and not read_only
        active_registry = self.plan_registry if planning or read_only else self.registry
        self.scheduler = ToolScheduler(active_registry)
        system_prompt = await build_system_prompt(
            self.working_dir,
            self.version,
            self.client.model,
            custom_instructions=self.custom_instructions,
            memory=self.memory_manager.current_index() if self.memory_manager else "",
        )

        user_message = ChatMessage(role="user", content=user_text)
        turn_messages = [copy.deepcopy(user_message)]
        user_committed = False
        unknown_rounds = 0

        for iteration in range(1, self.max_iterations + 1):
            yield AgentEvent(
                type="progress",
                iteration=iteration,
                max_iterations=self.max_iterations,
            )

            reminder = plan_reminder(iteration) if planning else None
            tool_definitions = active_registry.definitions()
            committed_history = self.conversation.get_messages()
            pending_messages = [] if user_committed else [user_message]
            candidate_request = LLMRequest(
                messages=[*committed_history, *pending_messages],
                tools=tool_definitions,
                system=system_prompt,
                reminder=reminder,
            )
            will_compact, before_tokens, _ = self.context_manager.auto_compact_status(
                candidate_request
            )
            if will_compact:
                yield AgentEvent(
                    type="compact",
                    compact=CompactEvent(
                        phase="auto_start",
                        before_tokens=before_tokens,
                        offloaded_results=self.context_manager.offloaded_results,
                    ),
                )
            prepared = await self.context_manager.prepare_request(
                committed_history,
                pending_messages,
                system_prompt,
                tool_definitions,
                reminder,
            )
            if prepared.compact is not None:
                phase = "auto_complete" if prepared.compact.success else "auto_failed"
                stats = prepared.compact.stats
                yield AgentEvent(
                    type="compact",
                    compact=CompactEvent(
                        phase=phase,
                        before_tokens=stats.before_tokens,
                        after_tokens=stats.after_tokens,
                        offloaded_results=stats.offloaded_results,
                        message=stats.error,
                    ),
                )
                if prepared.compact.success:
                    self.conversation.replace_messages(prepared.committed_history)
                    warning = self.conversation.take_persistence_warning()
                    if warning:
                        yield AgentEvent(type="session_warning", text=warning)
            if prepared.circuit_tripped:
                yield AgentEvent(
                    type="compact",
                    compact=CompactEvent(
                        phase="circuit_tripped",
                        before_tokens=before_tokens,
                        message="自动上下文压缩已连续失败 3 次，请使用 /compact 手动重试。",
                    ),
                )

            collector = StreamCollector()
            llm_request = LLMRequest(
                messages=prepared.request_messages,
                tools=tool_definitions,
                system=system_prompt,
                reminder=reminder,
            )
            stream = self.client.stream(llm_request)
            iterator = stream.__aiter__()
            stream_cancelled = False

            try:
                while True:
                    self.active_client_task = asyncio.create_task(anext(iterator))
                    try:
                        llm_event = await self.active_client_task
                    except StopAsyncIteration:
                        break
                    except asyncio.CancelledError:
                        if not self.cancel_requested:
                            raise
                        stream_cancelled = True
                        break
                    finally:
                        self.active_client_task = None

                    agent_event = collector.accept(llm_event)
                    if agent_event is not None:
                        yield agent_event
            except LLMError as error:
                yield AgentEvent(type="error", error=error, usage=self.task_usage)
                return
            finally:
                if stream_cancelled:
                    close = getattr(iterator, "aclose", None)
                    if close is not None:
                        await close()

            if stream_cancelled:
                yield AgentEvent(
                    type="cancelled",
                    text="当前任务已取消。",
                    usage=self.task_usage,
                )
                return

            try:
                response = collector.finish()
            except LLMError as error:
                yield AgentEvent(type="error", error=error, usage=self.task_usage)
                return

            self.task_usage = self.task_usage.add(response.usage)
            yield AgentEvent(type="usage", usage=self.task_usage)
            assistant_message = response.message
            self.context_manager.record_main_usage(
                llm_request,
                assistant_message,
                response.usage,
            )

            if not assistant_message.tool_calls:
                messages_to_commit = []
                if not user_committed:
                    messages_to_commit.append(user_message)
                messages_to_commit.append(assistant_message)
                self.conversation.commit_messages(messages_to_commit)
                turn_messages.append(copy.deepcopy(assistant_message))
                warning = self.conversation.take_persistence_warning()
                if warning:
                    yield AgentEvent(type="session_warning", text=warning)

                if planning:
                    self.has_plan = True
                self.completed_turns += 1
                if self.memory_manager is not None:
                    self.memory_manager.schedule_update(
                        self.client,
                        turn_messages,
                        self.completed_turns,
                        user_text,
                    )
                yield AgentEvent(
                    type="completed",
                    text=assistant_message.content,
                    usage=self.task_usage,
                )
                return

            raw_results = []
            async for tool_event in self._execute_tools(assistant_message.tool_calls):
                if tool_event.tool_result is not None:
                    raw_results.append(tool_event.tool_result)
                else:
                    yield tool_event
            results = await self.context_manager.process_tool_results(raw_results)
            if self.context_manager.last_offload_failures:
                yield AgentEvent(
                    type="context_warning",
                    text=(
                        f"{self.context_manager.last_offload_failures} 个大型工具结果落盘失败，"
                        "本轮已保留原始内容。"
                    ),
                )
            for result in results:
                yield AgentEvent(type="tool_end", tool_result=result)
            was_cancelled = self.cancel_requested

            messages_to_commit = []
            if not user_committed:
                messages_to_commit.append(user_message)
                user_committed = True
            messages_to_commit.extend(
                [
                    assistant_message,
                    ChatMessage(role="tool", tool_results=results),
                ]
            )
            self.conversation.commit_messages(messages_to_commit)
            turn_messages.extend(
                [
                    copy.deepcopy(assistant_message),
                    ChatMessage(role="tool", tool_results=copy.deepcopy(results)),
                ]
            )
            warning = self.conversation.take_persistence_warning()
            if warning:
                yield AgentEvent(type="session_warning", text=warning)

            if was_cancelled:
                yield AgentEvent(
                    type="cancelled",
                    text="当前任务已取消。",
                    usage=self.task_usage,
                )
                return

            if results and all(result.error_code == "unknown_tool" for result in results):
                unknown_rounds += 1
            else:
                unknown_rounds = 0

            if unknown_rounds >= self.unknown_tool_limit:
                yield AgentEvent(
                    type="limit",
                    text=UNKNOWN_TOOL_LIMIT_MESSAGE,
                    usage=self.task_usage,
                )
                return

            if iteration == self.max_iterations:
                message = (
                    f"已达到 Agent Loop 的 {self.max_iterations} 次迭代上限，不会继续请求模型。"
                )
                yield AgentEvent(type="limit", text=message, usage=self.task_usage)
                return

        # for 范围本身已经限制迭代数，这里只作为防御性兜底。
        yield AgentEvent(type="limit", text=ITERATION_LIMIT_MESSAGE, usage=self.task_usage)

    def replace_session(
        self,
        conversation: Conversation,
        context_manager: ContextManager,
        *,
        preserve_mode: bool = False,
    ) -> None:
        """恢复成功后一次替换会话对象，并清理旧计划状态。"""

        previous_mode = self.mode
        self.conversation = conversation
        self.context_manager = context_manager
        self.completed_turns = sum(
            1 for message in conversation.get_messages() if message.role == "user"
        )
        self.mode = previous_mode if preserve_mode else PermissionMode.DEFAULT
        self.has_plan = False
        self.cancel_requested = False

    async def _execute_tools(self, calls: list[ToolCall]):
        """先检查权限，再按原批次执行并保序返回结果。"""

        if self.scheduler is None:
            return

        batches = self.scheduler.partition(calls)

        for index, batch in enumerate(batches):
            if self.cancel_requested:
                for result in self._cancel_remaining_batches(batches[index:]):
                    yield AgentEvent(type="tool_end", tool_result=result)
                return

            for call in batch.calls:
                yield AgentEvent(type="tool_start", tool_call=call)

            results: list[ToolResult | None] = [None] * len(batch.calls)
            allowed_calls: list[ToolCall] = []
            allowed_indexes: list[int] = []

            for call_index, call in enumerate(batch.calls):
                permission = self.permission_engine.check(
                    call,
                    self.scheduler.registry.get(call.name),
                    self.mode,
                )
                if permission.decision is PermissionDecision.DENY:
                    results[call_index] = self._permission_denied_result(call, permission)
                    continue

                if permission.decision is PermissionDecision.ASK:
                    try:
                        exact_rule = make_exact_rule(call, self.working_dir)
                    except RuleParseError:
                        exact_rule = ""
                    future = self.approval_controller.begin(call.id)
                    yield AgentEvent(
                        type="permission_request",
                        permission_request=PermissionRequest(
                            call=call,
                            reason=permission.reason,
                            summary=self._permission_summary(call),
                            exact_rule=exact_rule,
                        ),
                    )
                    try:
                        choice = await future
                    except asyncio.CancelledError:
                        self.cancel_requested = True
                        break

                    if choice is ApprovalChoice.DENY_ONCE:
                        user_denial = PermissionResult(
                            PermissionDecision.DENY,
                            "user",
                            "用户拒绝了本次工具调用。",
                        )
                        results[call_index] = self._permission_denied_result(call, user_denial)
                        continue
                    if choice is ApprovalChoice.ALLOW_SESSION:
                        self.permission_engine.allow_for_session(call.name)
                    if choice is ApprovalChoice.ALLOW_ALWAYS:
                        try:
                            if not exact_rule:
                                raise RuleParseError("无法生成精确规则。")
                            self.permission_engine.rule_store.save_local_allow(exact_rule)
                        except (OSError, RuleParseError):
                            yield AgentEvent(
                                type="permission_warning",
                                text="永久权限保存失败，本次仍按允许一次执行。",
                            )

                allowed_indexes.append(call_index)
                allowed_calls.append(call)

            if self.cancel_requested:
                for result_index, call in enumerate(batch.calls):
                    if results[result_index] is None:
                        results[result_index] = self.scheduler.make_cancelled_results([call])[0]
                for result in results:
                    if result is not None:
                        yield AgentEvent(type="tool_end", tool_result=result)
                for result in self._cancel_remaining_batches(batches[index + 1 :]):
                    yield AgentEvent(type="tool_end", tool_result=result)
                return

            if allowed_calls:
                allowed_batch = ToolBatch(calls=allowed_calls, concurrent=batch.concurrent)
                executed = await self.scheduler.execute_batch(allowed_batch)
                for result_index, result in zip(allowed_indexes, executed, strict=True):
                    results[result_index] = result

            for call, result in zip(batch.calls, results, strict=True):
                if result is None:
                    result = ToolResult(
                        call_id=call.id,
                        tool_name=call.name,
                        success=False,
                        error_code="tool_error",
                        error_message="工具没有产生可用结果。",
                    )
                yield AgentEvent(type="tool_end", tool_result=result)

            if self.cancel_requested:
                for result in self._cancel_remaining_batches(batches[index + 1 :]):
                    yield AgentEvent(type="tool_end", tool_result=result)
                return

    @staticmethod
    def _permission_summary(call: ToolCall) -> str:
        """生成适合确认框显示的单行关键参数。"""

        arguments = call.arguments or {}
        if call.name == "Bash":
            value = arguments.get("command", "")
        elif call.name == "Glob":
            value = arguments.get("pattern", "")
        else:
            value = arguments.get("path", "")
        one_line = str(value).replace("\r", " ").replace("\n", " ")
        if len(one_line) > 160:
            one_line = one_line[:157] + "..."
        return f"{call.name}({one_line})"

    @staticmethod
    def _permission_denied_result(
        call: ToolCall,
        permission: PermissionResult,
    ) -> ToolResult:
        """把权限拒绝转换为可以安全回灌给模型的工具结果。"""

        if permission.source == "unknown_tool":
            error_code = "unknown_tool"
        elif permission.source == "invalid_arguments":
            error_code = "invalid_json"
        else:
            error_code = "permission_denied"
        return ToolResult(
            call_id=call.id,
            tool_name=call.name,
            success=False,
            error_code=error_code,
            error_message=permission.reason,
            metadata={
                "permission_source": permission.source,
                "matched_rule": permission.matched_rule,
            },
        )

    def _cancel_remaining_batches(self, batches: list[ToolBatch]) -> list[ToolResult]:
        if self.scheduler is None:
            return []
        calls = [call for batch in batches for call in batch.calls]
        return self.scheduler.make_cancelled_results(calls)
