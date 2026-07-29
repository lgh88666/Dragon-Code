"""Anthropic Messages 协议适配器。"""

import asyncio

from anthropic import AsyncAnthropic

from dragon_code.models import ChatMessage, ProviderConfig
from dragon_code.providers.base import BaseProvider, make_provider_error


class AnthropicProvider(BaseProvider):
    """把 Anthropic SDK 的流式响应转换为正文字符串。"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)

        client_args = {"api_key": config.api_key}
        if config.base_url:
            client_args["base_url"] = config.base_url
        self._client = AsyncAnthropic(**client_args)

    def _build_messages(self, messages: list[ChatMessage]) -> list[dict[str, str]]:
        """把项目内部消息转换为 Anthropic 消息。"""

        return [{"role": item.role, "content": item.content} for item in messages]

    def _build_request(self, messages: list[ChatMessage], system_prompt: str) -> dict:
        """组装 Anthropic Messages 请求参数。"""

        request = {
            "model": self.model,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": self._build_messages(messages),
        }
        if self.config.thinking:
            # 思考预算必须小于 max_tokens，否则 Anthropic 会拒绝请求。
            request["thinking"] = {"type": "enabled", "budget_tokens": 2048}
        return request

    async def stream(self, messages: list[ChatMessage], system_prompt: str):
        """只产出最终正文，thinking 事件在这里直接丢弃。"""

        request = self._build_request(messages, system_prompt)
        try:
            async with self._client.messages.stream(**request) as response:
                async for event in response:
                    if event.type == "text":
                        yield event.text
                    # thinking、签名和生命周期事件都不传给上层。
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise make_provider_error(error) from error
