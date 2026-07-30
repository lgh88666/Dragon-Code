"""单会话历史和一轮模型请求的协调逻辑。"""

import asyncio

from dragon_code.models import ChatMessage, TurnEvent
from dragon_code.providers.base import BaseProvider, ProviderError
from dragon_code.tools.registry import ToolRegistry

LIMIT_MESSAGE = "已达到 ch03 的单轮工具调用上限，本轮不会继续执行工具。"


class Conversation:
    """保存当前进程内已经成功完成的对话历史。"""

    def __init__(self):
        self._messages: list[ChatMessage] = []

    def get_messages(self) -> list[ChatMessage]:
        """返回历史副本，避免调用方改坏内部状态。"""

        return list(self._messages)

    def build_request_messages(self, user_text: str) -> list[ChatMessage]:
        """生成请求消息，但暂时不把用户输入写入历史。"""

        messages = self.get_messages()
        messages.append(ChatMessage(role="user", content=user_text))
        return messages

    def commit_messages(self, messages: list[ChatMessage]) -> None:
        """一次性保存一组已经完成的消息。"""

        self._messages.extend(messages)


class ChatSession:
    """连接 Conversation 与 Provider，完成一次流式对话。"""

    def __init__(
        self,
        provider: BaseProvider,
        conversation: Conversation,
        system_prompt: str,
        registry: ToolRegistry,
    ):
        self.provider = provider
        self.conversation = conversation
        self.system_prompt = system_prompt
        self.registry = registry

    async def stream_turn(self, user_text: str):
        """执行普通对话或一轮工具调用加一次最终续答。"""

        request_messages = self.conversation.build_request_messages(user_text)
        try:
            first_message = None
            async for event in self.provider.stream(
                request_messages,
                self.system_prompt,
                self.registry.definitions(),
            ):
                if event.type == "text_delta":
                    yield TurnEvent(type="text", text=event.text)
                elif event.type == "tool_call":
                    yield TurnEvent(type="tool_call", tool_call=event.tool_call)
                elif event.type == "completed":
                    first_message = event.message
        except asyncio.CancelledError:
            raise
        except ProviderError as error:
            yield TurnEvent(type="error", error=error)
            return

        if first_message is None:
            yield TurnEvent(
                type="error",
                error=ProviderError("invalid_response", "模型响应没有完整结束。"),
            )
            return

        user_message = ChatMessage(role="user", content=user_text)
        if not first_message.tool_calls:
            self.conversation.commit_messages([user_message, first_message])
            yield TurnEvent(type="completed", text=first_message.content)
            return

        results = []
        for call in first_message.tool_calls:
            result = await self.registry.execute(call)
            results.append(result)
            yield TurnEvent(type="tool_result", tool_result=result)

        tool_message = ChatMessage(role="tool", tool_results=results)
        followup_messages = request_messages + [first_message, tool_message]

        try:
            final_message = None
            async for event in self.provider.stream(
                followup_messages,
                self.system_prompt,
                self.registry.definitions(),
            ):
                if event.type == "text_delta":
                    yield TurnEvent(type="text", text=event.text)
                elif event.type == "completed":
                    final_message = event.message
                # 续答中的 tool_call 先收集，不交给注册中心。
        except asyncio.CancelledError:
            raise
        except ProviderError as error:
            yield TurnEvent(type="error", error=error)
            return

        if final_message is None:
            yield TurnEvent(
                type="error",
                error=ProviderError("invalid_response", "模型续答没有完整结束。"),
            )
            return

        if final_message.tool_calls:
            visible_text = final_message.content
            local_text = f"{visible_text}\n\n{LIMIT_MESSAGE}".strip()
            local_message = ChatMessage(role="assistant", content=local_text)
            self.conversation.commit_messages(
                [user_message, first_message, tool_message, local_message]
            )
            yield TurnEvent(
                type="limit",
                text=LIMIT_MESSAGE,
                tool_call=final_message.tool_calls[0],
            )
            return

        self.conversation.commit_messages(
            [user_message, first_message, tool_message, final_message]
        )
        yield TurnEvent(type="completed", text=final_message.content)
