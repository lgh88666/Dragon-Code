"""Dragon Code 的 ReAct Agent Loop。"""

import asyncio

from dragon_code.models import AgentEvent, ChatMessage, TokenUsage, ToolCall, ToolResult
from dragon_code.prompt import build_agent_prompt
from dragon_code.providers.base import BaseProvider, ProviderError
from dragon_code.session import Conversation
from dragon_code.stream_collector import StreamCollector
from dragon_code.tool_scheduler import ToolBatch, ToolScheduler
from dragon_code.tools.registry import ToolRegistry

ITERATION_LIMIT_MESSAGE = "已达到 Agent Loop 的 50 次迭代上限。"
UNKNOWN_TOOL_LIMIT_MESSAGE = "模型连续请求未知工具，Agent Loop 已停止。"


class Agent:
    """连接模型、工具和历史，持续工作到任务完成。"""

    def __init__(
        self,
        provider: BaseProvider,
        conversation: Conversation,
        system_prompt: str,
        registry: ToolRegistry,
        max_iterations: int = 50,
        unknown_tool_limit: int = 3,
    ):
        self.provider = provider
        self.conversation = conversation
        self.system_prompt = system_prompt
        self.registry = registry
        self.plan_registry = registry.subset({"Read", "Glob", "Grep"})
        self.max_iterations = max_iterations
        self.unknown_tool_limit = unknown_tool_limit

        self.mode = "default"
        self.has_plan = False
        self.cancel_requested = False
        self.task_usage = TokenUsage(0, 0)
        self.active_provider_task: asyncio.Task | None = None
        self.scheduler: ToolScheduler | None = None

    def enter_plan_mode(self) -> None:
        """进入持续计划模式；从 Default 进入时清空旧计划标记。"""

        if self.mode != "plan":
            self.has_plan = False
        self.mode = "plan"

    def can_execute_plan(self) -> bool:
        return self.mode == "plan" and self.has_plan

    def enter_default_mode(self) -> None:
        self.mode = "default"
        self.has_plan = False

    def request_cancel(self) -> None:
        """停止当前网络等待或工具批次，外层循环负责合法收尾。"""

        self.cancel_requested = True
        if self.active_provider_task is not None and not self.active_provider_task.done():
            self.active_provider_task.cancel()
        if self.scheduler is not None:
            self.scheduler.cancel_active()

    async def run(self, user_text: str):
        """运行一个完整任务，异步产出界面所需事件。"""

        self.cancel_requested = False
        self.task_usage = TokenUsage(0, 0)
        active_registry = self.plan_registry if self.mode == "plan" else self.registry
        self.scheduler = ToolScheduler(active_registry)
        system_prompt = build_agent_prompt(self.system_prompt, self.mode)

        request_messages = self.conversation.build_request_messages(user_text)
        user_message = request_messages[-1]
        user_committed = False
        unknown_rounds = 0

        for iteration in range(1, self.max_iterations + 1):
            yield AgentEvent(
                type="progress",
                iteration=iteration,
                max_iterations=self.max_iterations,
            )

            collector = StreamCollector()
            stream = self.provider.stream(
                request_messages,
                system_prompt,
                active_registry.definitions(),
            )
            iterator = stream.__aiter__()
            stream_cancelled = False

            try:
                while True:
                    self.active_provider_task = asyncio.create_task(anext(iterator))
                    try:
                        provider_event = await self.active_provider_task
                    except StopAsyncIteration:
                        break
                    except asyncio.CancelledError:
                        if not self.cancel_requested:
                            raise
                        stream_cancelled = True
                        break
                    finally:
                        self.active_provider_task = None

                    agent_event = collector.accept(provider_event)
                    if agent_event is not None:
                        yield agent_event
            except ProviderError as error:
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
            except ProviderError as error:
                yield AgentEvent(type="error", error=error, usage=self.task_usage)
                return

            self.task_usage = self.task_usage.add(response.usage)
            yield AgentEvent(type="usage", usage=self.task_usage)
            assistant_message = response.message

            if not assistant_message.tool_calls:
                messages_to_commit = []
                if not user_committed:
                    messages_to_commit.append(user_message)
                messages_to_commit.append(assistant_message)
                self.conversation.commit_messages(messages_to_commit)

                if self.mode == "plan":
                    self.has_plan = True
                yield AgentEvent(
                    type="completed",
                    text=assistant_message.content,
                    usage=self.task_usage,
                )
                return

            results = []
            async for tool_event in self._execute_tools(assistant_message.tool_calls):
                yield tool_event
                if tool_event.tool_result is not None:
                    results.append(tool_event.tool_result)
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
            request_messages = self.conversation.get_messages()

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

    async def _execute_tools(self, calls: list[ToolCall]):
        """按批次产生工具开始与结束事件。"""

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

            batch_results = await self.scheduler.execute_batch(batch)
            for result in batch_results:
                yield AgentEvent(type="tool_end", tool_result=result)

            if self.cancel_requested:
                for result in self._cancel_remaining_batches(batches[index + 1 :]):
                    yield AgentEvent(type="tool_end", tool_result=result)
                return

    def _cancel_remaining_batches(self, batches: list[ToolBatch]) -> list[ToolResult]:
        if self.scheduler is None:
            return []
        calls = [call for batch in batches for call in batch.calls]
        return self.scheduler.make_cancelled_results(calls)
