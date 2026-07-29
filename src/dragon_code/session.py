"""单会话历史和一轮模型请求的协调逻辑。"""

import asyncio

from dragon_code.models import ChatMessage, TurnEvent
from dragon_code.providers.base import BaseProvider, ProviderError


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

    def commit_turn(self, user_text: str, assistant_text: str) -> None:
        """请求成功后，一次性保存用户和助手消息。"""

        self._messages.append(ChatMessage(role="user", content=user_text))
        self._messages.append(ChatMessage(role="assistant", content=assistant_text))


class ChatSession:
    """连接 Conversation 与 Provider，完成一次流式对话。"""

    def __init__(
        self,
        provider: BaseProvider,
        conversation: Conversation,
        system_prompt: str,
    ):
        self.provider = provider
        self.conversation = conversation
        self.system_prompt = system_prompt

    async def stream_turn(self, user_text: str):
        """逐步产生正文事件，并在成功后提交完整历史。"""

        request_messages = self.conversation.build_request_messages(user_text)
        reply_parts: list[str] = []

        try:
            async for text in self.provider.stream(request_messages, self.system_prompt):
                reply_parts.append(text)
                yield TurnEvent(type="text", text=text)
        except asyncio.CancelledError:
            raise
        except ProviderError as error:
            yield TurnEvent(type="error", error=error)
            return

        full_reply = "".join(reply_parts)
        self.conversation.commit_turn(user_text, full_reply)
        yield TurnEvent(type="completed", text=full_reply)
