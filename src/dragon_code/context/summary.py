"""结构化摘要的纯函数。"""

from __future__ import annotations

import copy
import json
import math
import re
from dataclasses import asdict

from dragon_code.context.constants import (
    CHARS_PER_TOKEN,
    RECENT_RAW_MESSAGE_MIN,
    RECENT_RAW_TOKEN_MIN,
)
from dragon_code.models import ChatMessage

SUMMARY_SECTION_TITLES = (
    "主要请求和意图",
    "关键技术概念",
    "文件和代码段",
    "错误与修复",
    "问题解决过程",
    "用户消息原文",
    "待办任务",
    "当前工作和停止位置",
    "可能的下一步",
)

SUMMARY_SYSTEM_PROMPT = """你负责压缩一段编程 Agent 对话。
严禁调用任何工具；本请求没有工具可用，也不得伪造工具调用。
先在 <analysis> 中写临时分析草稿，再在 <summary> 中写正式摘要。
正式摘要必须包含以下九个标题，信息不足也保留标题并写“无”：
1. 主要请求和意图
2. 关键技术概念
3. 文件和代码段
4. 错误与修复
5. 问题解决过程
6. 用户消息原文
7. 待办任务
8. 当前工作和停止位置
9. 可能的下一步
用户消息尽量逐条保留原始表达，不要把不确定的代码细节写成事实。
严禁调用任何工具；只返回 <analysis> 和一个非空 <summary>。"""

COMPACT_BOUNDARY = (
    "[上下文压缩边界]\n"
    "以上摘要用于延续任务，但不等同于文件原文。需要文件细节、错误原文或精确代码时，"
    "必须使用 Read 工具重新读取对应路径；不得依据摘要脑补代码。"
)


def serialize_messages(messages: list[ChatMessage]) -> str:
    """把协议无关历史稳定序列化为摘要输入。"""

    payload = [asdict(message) for message in messages]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str)


def build_summary_user_prompt(messages: list[ChatMessage]) -> str:
    """构造只包含历史的摘要用户消息。"""

    return (
        "请压缩下面的 Dragon Code 对话历史。严禁调用任何工具。\n\n"
        "<conversation>\n"
        f"{serialize_messages(messages)}\n"
        "</conversation>\n\n"
        "先输出 <analysis> 草稿，再输出唯一的 <summary> 正式摘要。"
        "严禁调用任何工具。"
    )


def extract_summary(text: str) -> str:
    """只接受唯一、非空且闭合的 summary 区间。"""

    matches = re.findall(r"<summary>(.*?)</summary>", text, flags=re.DOTALL)
    if len(matches) != 1 or not matches[0].strip():
        raise ValueError("摘要响应缺少唯一、非空的 <summary>")
    outside = re.sub(r"<summary>.*?</summary>", "", text, flags=re.DOTALL)
    if "<summary>" in outside or "</summary>" in outside:
        raise ValueError("摘要响应包含歧义标签")
    summary = matches[0].strip()
    missing = [title for title in SUMMARY_SECTION_TITLES if title not in summary]
    if missing:
        raise ValueError("摘要响应缺少固定部分")
    return summary


def estimate_message_tokens(message: ChatMessage) -> int:
    """使用本章批准的字符比例估算单条消息。"""

    chars = len(serialize_messages([message]))
    return math.ceil(chars / CHARS_PER_TOKEN)


def _message_groups(messages: list[ChatMessage]) -> list[list[ChatMessage]]:
    groups: list[list[ChatMessage]] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        group = [message]
        if (
            message.role == "assistant"
            and message.tool_calls
            and index + 1 < len(messages)
            and messages[index + 1].role == "tool"
        ):
            group.append(messages[index + 1])
            index += 1
        groups.append(group)
        index += 1
    return groups


def select_recent_messages(
    messages: list[ChatMessage],
    *,
    min_tokens: int = RECENT_RAW_TOKEN_MIN,
    min_messages: int = RECENT_RAW_MESSAGE_MIN,
) -> list[ChatMessage]:
    """从尾部选择同时满足 Token 和消息数下界的完整消息组。"""

    selected_groups: list[list[ChatMessage]] = []
    token_count = 0
    message_count = 0
    for group in reversed(_message_groups(messages)):
        selected_groups.append(group)
        token_count += sum(estimate_message_tokens(message) for message in group)
        message_count += len(group)
        if token_count >= min_tokens and message_count >= min_messages:
            break

    selected = [message for group in reversed(selected_groups) for message in group]
    return copy.deepcopy(selected)


def build_compacted_history(
    summary: str,
    recent_messages: list[ChatMessage],
) -> list[ChatMessage]:
    """构造摘要边界消息和近期原文组成的新历史。"""

    boundary_message = ChatMessage(
        role="user",
        content=f"<summary>\n{summary.strip()}\n</summary>\n\n{COMPACT_BOUNDARY}",
    )
    return [boundary_message, *copy.deepcopy(recent_messages)]
