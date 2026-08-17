"""构造合法且与父会话隔离的 Fork 消息。"""

import copy

from dragon_code.models import ChatMessage, ToolResult

FORK_BOILERPLATE_TAG = "<fork-boilerplate>"
FORK_BOILERPLATE = f"""{FORK_BOILERPLATE_TAG}
这是一个独立 Fork 子任务。直接完成分配的任务，不向用户提问或请求交互确认；
不要扩大任务范围，不要创建新的子 Agent，最后只返回简短而完整的结果。
</fork-boilerplate>"""


def _placeholder(call_id: str, tool_name: str) -> ToolResult:
    return ToolResult(
        call_id=call_id,
        tool_name=tool_name,
        success=False,
        error_code="fork_placeholder",
        error_message="父 Agent 正在处理该工具调用，Fork 子任务无需等待或重复执行。",
    )


def _repair_pending_tool_calls(messages: list[ChatMessage]) -> list[ChatMessage]:
    repaired: list[ChatMessage] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        repaired.append(message)
        if message.role != "assistant" or not message.tool_calls:
            index += 1
            continue

        next_message = messages[index + 1] if index + 1 < len(messages) else None
        existing_ids: set[str] = set()
        if next_message is not None and next_message.role == "tool":
            existing_ids = {result.call_id for result in next_message.tool_results}
        missing = [call for call in message.tool_calls if call.id not in existing_ids]
        if missing and next_message is not None and next_message.role == "tool":
            next_message.tool_results.extend(_placeholder(call.id, call.name) for call in missing)
        elif missing:
            repaired.append(
                ChatMessage(
                    role="tool",
                    tool_results=[_placeholder(call.id, call.name) for call in missing],
                )
            )
        index += 1
    return repaired


def build_fork_messages(
    committed: list[ChatMessage],
    pending_assistant: ChatMessage | None,
    task_prompt: str,
) -> list[ChatMessage]:
    """复制父历史、补齐工具结果并追加 Fork 任务。"""

    messages = copy.deepcopy(committed)
    if pending_assistant is not None:
        messages.append(copy.deepcopy(pending_assistant))
    messages = _repair_pending_tool_calls(messages)
    messages.append(ChatMessage(role="user", content=f"{FORK_BOILERPLATE}\n\n任务：{task_prompt}"))
    return messages


def is_fork_context(messages: list[ChatMessage]) -> bool:
    return any(
        message.role == "user" and FORK_BOILERPLATE_TAG in message.content for message in messages
    )
