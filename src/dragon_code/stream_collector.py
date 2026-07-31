"""收集一次 Provider 流，同时把正文增量实时交给界面。"""

from dataclasses import dataclass

from dragon_code.models import AgentEvent, ChatMessage, ProviderEvent, TokenUsage
from dragon_code.providers.base import ProviderError


@dataclass
class CollectedResponse:
    """一次完整模型响应。"""

    message: ChatMessage
    usage: TokenUsage


class StreamCollector:
    """只保存单次请求的完整消息与用量。"""

    def __init__(self):
        self.message: ChatMessage | None = None
        self.usage = TokenUsage()

    def accept(self, event: ProviderEvent) -> AgentEvent | None:
        """接收 Provider 事件，正文增量立即转换为 Agent 事件。"""

        if event.type == "text_delta":
            return AgentEvent(type="text", text=event.text)
        if event.type == "usage" and event.usage is not None:
            self.usage = event.usage
        elif event.type == "completed":
            self.message = event.message
        return None

    def finish(self) -> CollectedResponse:
        """流结束后返回完整结果。"""

        if self.message is None:
            raise ProviderError("invalid_response", "模型响应没有完整结束。")
        return CollectedResponse(message=self.message, usage=self.usage)
