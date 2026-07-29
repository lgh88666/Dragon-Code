"""OpenAI Chat Completions 协议适配器。"""

import asyncio

from openai import AsyncOpenAI

from dragon_code.models import ChatMessage, ProviderConfig
from dragon_code.providers.base import BaseProvider, make_provider_error


class OpenAIProvider(BaseProvider):
    """把 OpenAI SDK 的流式响应转换为正文字符串。"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)

        client_args = {"api_key": config.api_key}
        if config.base_url:
            client_args["base_url"] = config.base_url
        self._client = AsyncOpenAI(**client_args)

    def _build_messages(
        self, messages: list[ChatMessage], system_prompt: str
    ) -> list[dict[str, str]]:
        """把 System Prompt 与完整历史转换为 OpenAI 消息。"""

        result = [{"role": "system", "content": system_prompt}]
        result.extend({"role": item.role, "content": item.content} for item in messages)
        return result

    async def stream(self, messages: list[ChatMessage], system_prompt: str):
        """通过 Chat Completions 流式产出正文。"""

        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=self._build_messages(messages, system_prompt),
                stream=True,
            )
            async for chunk in response:
                if not chunk.choices:
                    continue
                text = chunk.choices[0].delta.content
                if text:
                    yield text
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise make_provider_error(error) from error
