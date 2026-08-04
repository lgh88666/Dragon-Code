"""多个测试模块共用的假 LLM Client。"""

import asyncio

from dragon_code.clients.base import LLMClient, LLMError
from dragon_code.models import ChatMessage, LLMEvent, ProviderConfig


class FakeClient(LLMClient):
    """按预设分片返回内容，也可以模拟失败或延迟。"""

    def __init__(
        self,
        chunks: list[str] | None = None,
        events: list[LLMEvent] | None = None,
        responses: list[list[LLMEvent] | LLMError] | None = None,
        error: LLMError | None = None,
        delay: float = 0,
    ):
        config = ProviderConfig("Fake", "openai", "fake-key", "fake-model")
        super().__init__(config)
        self.chunks = chunks or []
        self.events = events
        self.responses = list(responses or [])
        self.error = error
        self.delay = delay
        self.requests = []
        self.received_messages = []
        self.received_system_prompt = ""
        self.received_tools = []

    async def stream(self, request):
        self.received_messages = list(request.messages)
        self.received_system_prompt = request.system
        self.received_tools = list(request.tools)
        self.requests.append(request)

        if self.error:
            raise self.error
        if self.responses:
            response = self.responses.pop(0)
            if isinstance(response, LLMError):
                raise response
            for event in response:
                yield event
            return
        if self.events is not None:
            for event in self.events:
                yield event
            return

        reply = ""
        for chunk in self.chunks:
            if self.delay:
                await asyncio.sleep(self.delay)
            reply += chunk
            yield LLMEvent(type="text_delta", text=chunk)
        yield LLMEvent(
            type="completed",
            message=ChatMessage(role="assistant", content=reply),
        )
