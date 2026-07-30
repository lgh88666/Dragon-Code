"""多个测试模块共用的假 Provider。"""

import asyncio

from dragon_code.models import ChatMessage, ProviderConfig, ProviderEvent
from dragon_code.providers.base import BaseProvider, ProviderError


class FakeProvider(BaseProvider):
    """按预设分片返回内容，也可以模拟失败或延迟。"""

    def __init__(
        self,
        chunks: list[str] | None = None,
        events: list[ProviderEvent] | None = None,
        error: ProviderError | None = None,
        delay: float = 0,
    ):
        config = ProviderConfig("Fake", "openai", "fake-key", "fake-model")
        super().__init__(config)
        self.chunks = chunks or []
        self.events = events
        self.error = error
        self.delay = delay
        self.received_messages = []
        self.received_system_prompt = ""
        self.received_tools = []

    async def stream(self, messages, system_prompt, tools):
        self.received_messages = list(messages)
        self.received_system_prompt = system_prompt
        self.received_tools = list(tools)

        if self.error:
            raise self.error
        if self.events is not None:
            for event in self.events:
                yield event
            return

        reply = ""
        for chunk in self.chunks:
            if self.delay:
                await asyncio.sleep(self.delay)
            reply += chunk
            yield ProviderEvent(type="text_delta", text=chunk)
        yield ProviderEvent(
            type="completed",
            message=ChatMessage(role="assistant", content=reply),
        )
