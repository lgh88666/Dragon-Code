"""Anthropic Messages 协议适配器。"""

import asyncio
import json

from anthropic import AsyncAnthropic

from dragon_code.models import (
    ChatMessage,
    ProviderConfig,
    ProviderEvent,
    ToolCall,
    ToolDefinition,
)
from dragon_code.providers.base import BaseProvider, make_provider_error


class AnthropicProvider(BaseProvider):
    """把 Anthropic SDK 的流式响应转换为正文字符串。"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)

        client_args = {"api_key": config.api_key}
        if config.base_url:
            client_args["base_url"] = config.base_url
        self._client = AsyncAnthropic(**client_args)

    def _build_messages(self, messages: list[ChatMessage]) -> list[dict]:
        """把项目内部消息转换为 Anthropic 消息。"""

        result = []
        for item in messages:
            if item.role == "tool":
                result.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_result.call_id,
                                "content": tool_result.to_model_text(),
                                "is_error": not tool_result.success,
                            }
                            for tool_result in item.tool_results
                        ],
                    }
                )
                continue
            if item.role == "assistant" and (item.hidden_blocks or item.tool_calls):
                content: list[dict] = [dict(block) for block in item.hidden_blocks]
                if item.content:
                    content.append({"type": "text", "text": item.content})
                content.extend(
                    {
                        "type": "tool_use",
                        "id": call.id,
                        "name": call.name,
                        "input": call.arguments or {},
                    }
                    for call in item.tool_calls
                )
                result.append({"role": "assistant", "content": content})
                continue
            result.append({"role": item.role, "content": item.content})
        return result

    def _build_tools(self, tools: list[ToolDefinition]) -> list[dict]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in tools
        ]

    def _build_request(
        self,
        messages: list[ChatMessage],
        system_prompt: str,
        tools: list[ToolDefinition],
    ) -> dict:
        """组装 Anthropic Messages 请求参数。"""

        request = {
            "model": self.model,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": self._build_messages(messages),
            "tools": self._build_tools(tools),
        }
        if self.config.thinking:
            # 思考预算必须小于 max_tokens，否则 Anthropic 会拒绝请求。
            request["thinking"] = {"type": "enabled", "budget_tokens": 2048}
        return request

    async def stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str,
        tools: list[ToolDefinition],
    ):
        """将 Anthropic 内容块转换为统一事件。"""

        request = self._build_request(messages, system_prompt, tools)
        try:
            async with self._client.messages.stream(**request) as response:
                reply_parts: list[str] = []
                buffers: dict[int, dict[str, str]] = {}
                calls: list[ToolCall] = []
                hidden_blocks: list[dict] = []
                async for event in response:
                    if event.type == "text":
                        reply_parts.append(event.text)
                        yield ProviderEvent(type="text_delta", text=event.text)
                        continue
                    if event.type == "content_block_start":
                        block = event.content_block
                        if getattr(block, "type", "") == "tool_use":
                            buffers[event.index] = {
                                "id": block.id,
                                "name": block.name,
                                "arguments": "",
                            }
                        continue
                    if event.type == "input_json":
                        buffer = buffers.setdefault(
                            event.index,
                            {"id": "", "name": "", "arguments": ""},
                        )
                        buffer["arguments"] += event.partial_json
                        continue
                    if event.type == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        if getattr(delta, "type", "") == "input_json_delta":
                            buffer = buffers.setdefault(
                                event.index,
                                {"id": "", "name": "", "arguments": ""},
                            )
                            buffer["arguments"] += delta.partial_json
                        continue
                    if event.type != "content_block_stop":
                        continue

                    block = event.content_block
                    block_type = getattr(block, "type", "")
                    if block_type in {"thinking", "redacted_thinking"}:
                        hidden_blocks.append(self._block_to_dict(block))
                    if block_type != "tool_use":
                        continue

                    buffer = buffers.get(
                        event.index,
                        {"id": block.id, "name": block.name, "arguments": ""},
                    )
                    raw = buffer["arguments"]
                    if raw:
                        try:
                            arguments = json.loads(raw)
                            parse_error = ""
                        except json.JSONDecodeError as error:
                            arguments = None
                            parse_error = f"工具参数 JSON 无效：{error.msg}"
                    else:
                        arguments = dict(getattr(block, "input", {}) or {})
                        parse_error = ""
                        raw = json.dumps(arguments, ensure_ascii=False)
                    call = ToolCall(
                        id=buffer["id"] or block.id,
                        name=buffer["name"] or block.name,
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
                    hidden_blocks=hidden_blocks,
                )
                yield ProviderEvent(type="completed", message=message)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise make_provider_error(error) from error

    @staticmethod
    def _block_to_dict(block) -> dict:
        """把 SDK 内容块转成不依赖 SDK 类型的普通字典。"""

        if hasattr(block, "model_dump"):
            return block.model_dump()
        return dict(vars(block))
