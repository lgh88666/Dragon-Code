"""ChatMessage 与 JSONL 字典的双向转换。"""

from __future__ import annotations

from typing import Any

from dragon_code.models import ChatMessage, ToolCall, ToolResult


class SessionRecordError(ValueError):
    """一整行会话记录无法安全恢复。"""


def message_to_record(
    message: ChatMessage,
    timestamp: int,
    model: str | None = None,
) -> dict[str, Any]:
    """把完整协议无关消息转成可写入 JSON 的字典。"""

    record: dict[str, Any] = {
        "type": "message",
        "role": message.role,
        "content": message.content,
        "tool_calls": [
            {
                "id": call.id,
                "name": call.name,
                "arguments": call.arguments,
                "raw_arguments": call.raw_arguments,
                "parse_error": call.parse_error,
            }
            for call in message.tool_calls
        ],
        "tool_results": [
            {
                "call_id": result.call_id,
                "tool_name": result.tool_name,
                "success": result.success,
                "content": result.content,
                "error_code": result.error_code,
                "error_message": result.error_message,
                "metadata": result.metadata,
                "truncated": result.truncated,
            }
            for result in message.tool_results
        ],
        "hidden_blocks": message.hidden_blocks,
        "timestamp": timestamp,
    }
    if model:
        record["model"] = model
    return record


def record_to_message(record: dict[str, Any]) -> ChatMessage:
    """校验一整条消息记录并恢复所有工具和隐藏字段。"""

    if record.get("type", "message") != "message":
        raise SessionRecordError("记录不是消息")
    role = record.get("role")
    content = record.get("content", "")
    tool_calls_data = record.get("tool_calls", [])
    tool_results_data = record.get("tool_results", [])
    hidden_blocks = record.get("hidden_blocks", [])
    if not isinstance(role, str) or not isinstance(content, str):
        raise SessionRecordError("消息角色或正文类型错误")
    if not isinstance(tool_calls_data, list) or not isinstance(tool_results_data, list):
        raise SessionRecordError("工具字段类型错误")
    if not isinstance(hidden_blocks, list) or not all(
        isinstance(block, dict) for block in hidden_blocks
    ):
        raise SessionRecordError("隐藏内容块类型错误")

    try:
        tool_calls = [_tool_call_from_dict(item) for item in tool_calls_data]
        tool_results = [_tool_result_from_dict(item) for item in tool_results_data]
    except (KeyError, TypeError, ValueError) as error:
        raise SessionRecordError("工具记录字段错误") from error
    return ChatMessage(
        role=role,
        content=content,
        tool_calls=tool_calls,
        tool_results=tool_results,
        hidden_blocks=hidden_blocks,
    )


def compact_record(timestamp: int) -> dict[str, Any]:
    """生成追加式压缩边界。"""

    return {"type": "compact", "timestamp": timestamp}


def _tool_call_from_dict(data: object) -> ToolCall:
    if not isinstance(data, dict):
        raise TypeError("tool_call 必须是对象")
    arguments = data.get("arguments")
    if arguments is not None and not isinstance(arguments, dict):
        raise TypeError("arguments 必须是对象或 null")
    return ToolCall(
        id=_required_string(data, "id"),
        name=_required_string(data, "name"),
        arguments=arguments,
        raw_arguments=_optional_string(data, "raw_arguments"),
        parse_error=_optional_string(data, "parse_error"),
    )


def _tool_result_from_dict(data: object) -> ToolResult:
    if not isinstance(data, dict):
        raise TypeError("tool_result 必须是对象")
    success = data.get("success")
    metadata = data.get("metadata", {})
    truncated = data.get("truncated", False)
    if not isinstance(success, bool) or not isinstance(metadata, dict):
        raise TypeError("工具结果类型错误")
    if not isinstance(truncated, bool):
        raise TypeError("truncated 必须是布尔值")
    return ToolResult(
        call_id=_required_string(data, "call_id"),
        tool_name=_required_string(data, "tool_name"),
        success=success,
        content=_optional_string(data, "content"),
        error_code=_optional_string(data, "error_code"),
        error_message=_optional_string(data, "error_message"),
        metadata=metadata,
        truncated=truncated,
    )


def _required_string(data: dict, key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} 必须是字符串")
    return value


def _optional_string(data: dict, key: str) -> str:
    value = data.get(key, "")
    if not isinstance(value, str):
        raise TypeError(f"{key} 必须是字符串")
    return value
