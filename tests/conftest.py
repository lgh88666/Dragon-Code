"""多个测试模块共用的假 Provider。"""

import asyncio

from dragon_code.models import ProviderConfig
from dragon_code.providers.base import BaseProvider, ProviderError


class FakeProvider(BaseProvider):
    """按预设分片返回内容，也可以模拟失败或延迟。"""

    def __init__(
        self,
        chunks: list[str] | None = None,
        error: ProviderError | None = None,
        delay: float = 0,
    ):
        config = ProviderConfig("Fake", "openai", "fake-key", "fake-model")
        super().__init__(config)
        self.chunks = chunks or []
        self.error = error
        self.delay = delay
        self.received_messages = []
        self.received_system_prompt = ""

    async def stream(self, messages, system_prompt):
        self.received_messages = list(messages)
        self.received_system_prompt = system_prompt

        if self.error:
            raise self.error
        for chunk in self.chunks:
            if self.delay:
                await asyncio.sleep(self.delay)
            yield chunk
