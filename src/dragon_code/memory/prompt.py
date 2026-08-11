"""构造自动记忆专用的无工具请求。"""

from __future__ import annotations

import json

from dragon_code.models import ChatMessage, LLMRequest, SystemPrompt

MEMORY_SYSTEM_PROMPT = """你是 Dragon Code 的记忆整理器。
只判断本轮是否产生值得跨会话保留的信息，不回答用户问题，不调用工具。
输出必须是 JSON 数组，数组元素只能是 create、update、delete 操作；没有变化时输出 []。

记忆类型与位置：
- user_preference、correction_feedback：level 必须为 user
- project_knowledge、reference_material：level 必须为 project

create 字段：action、level、memory_type、title、slug、content。
update 字段：action、level、filename、title、content。
delete 字段：action、level、filename。
先对照完整索引去重；只有稳定、有复用价值的信息才保存。"""


def build_memory_request(
    turn_messages: list[ChatMessage],
    current_index: str,
) -> LLMRequest:
    """把完成回合和索引转成不携带工具的独立请求。"""

    snapshot = [
        {
            "role": message.role,
            "content": message.content,
            "tool_calls": [call.name for call in message.tool_calls],
            "tool_results": [
                {"tool": result.tool_name, "success": result.success}
                for result in message.tool_results
            ],
        }
        for message in turn_messages
    ]
    user_prompt = (
        "当前记忆索引：\n"
        f"{current_index or '(empty)'}\n\n"
        "刚自然完成的回合：\n"
        f"{json.dumps(snapshot, ensure_ascii=False)}\n\n"
        "请只输出 JSON 操作数组。"
    )
    return LLMRequest(
        messages=[ChatMessage("user", user_prompt)],
        tools=[],
        system=SystemPrompt(stable=MEMORY_SYSTEM_PROMPT, environment=""),
    )
