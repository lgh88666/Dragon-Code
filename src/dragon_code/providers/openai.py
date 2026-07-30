"""OpenAI Chat Completions 协议适配器。"""

import asyncio
import json

from openai import AsyncOpenAI

from dragon_code.models import (
    ChatMessage,
    ProviderConfig,
    ProviderEvent,
    ToolCall,
    ToolDefinition,
)
from dragon_code.providers.base import BaseProvider, make_provider_error


class OpenAIProvider(BaseProvider):
    """把 OpenAI SDK 的流式响应转换为正文字符串。"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)

        client_args = {"api_key": config.api_key}
        if config.base_url:
            client_args["base_url"] = config.base_url
        self._client = AsyncOpenAI(**client_args)

    def _build_messages(self, messages: list[ChatMessage], system_prompt: str) -> list[dict]:
        """把 System Prompt 与完整历史转换为 OpenAI 消息。"""

        result = [{"role": "system", "content": system_prompt}]
        for item in messages:
            if item.role == "tool":
                for tool_result in item.tool_results:
                    result.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_result.call_id,
                            "content": tool_result.to_model_text(),
                        }
                    )
                continue

            message: dict = {"role": item.role, "content": item.content}
            if item.role == "assistant" and item.tool_calls:
                message["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": call.raw_arguments
                            or json.dumps(call.arguments or {}, ensure_ascii=False),
                        },
                    }
                    for call in item.tool_calls
                ]
            result.append(message)
        return result

    def _build_tools(self, tools: list[ToolDefinition]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in tools
        ]

    async def stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str,
        tools: list[ToolDefinition],
    ):
        """通过 Chat Completions 流式产出统一事件。"""

        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=self._build_messages(messages, system_prompt),
                tools=self._build_tools(tools),
                stream=True,
            )
            reply_parts: list[str] = []
            buffers: dict[int, dict[str, str]] = {}
            async for chunk in response:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                text = getattr(delta, "content", None)
                if text:
                    reply_parts.append(text)
                    yield ProviderEvent(type="text_delta", text=text)

                for part in getattr(delta, "tool_calls", None) or []:
                    buffer = buffers.setdefault(
                        part.index,
                        {"id": "", "name": "", "arguments": ""},
                    )
                    if getattr(part, "id", None):
                        buffer["id"] += part.id
                    function = getattr(part, "function", None)
                    if function is not None:
                        if getattr(function, "name", None):
                            buffer["name"] += function.name
                        if getattr(function, "arguments", None):
                            buffer["arguments"] += function.arguments

            calls = []
            for index in sorted(buffers):
                buffer = buffers[index]
                raw = buffer["arguments"]
                try:
                    arguments = json.loads(raw or "{}")
                    parse_error = ""
                except json.JSONDecodeError as error:
                    arguments = None
                    parse_error = f"工具参数 JSON 无效：{error.msg}"
                call = ToolCall(
                    id=buffer["id"] or f"call_{index}",
                    name=buffer["name"],
                    arguments=arguments,
                    raw_arguments=raw,
                    parse_error=parse_error,
                )
                calls.append(call)
                yield ProviderEvent(type="tool_call", tool_call=call)

            message = ChatMessage(
                role="assistant",
                content="".join(reply_parts),
                tool_calls=calls,
            )
            yield ProviderEvent(type="completed", message=message)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise make_provider_error(error) from error
