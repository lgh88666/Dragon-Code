"""项目各模块共享的简单数据模型。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dragon_code.permissions.models import PermissionRequest


@dataclass
class ProviderConfig:
    """单个模型服务的配置。"""

    name: str
    protocol: str
    api_key: str = field(repr=False)
    model: str
    base_url: str | None = None
    thinking: bool = False


@dataclass
class AppConfig:
    """Dragon Code 的完整配置。"""

    providers: list[ProviderConfig]


@dataclass
class ToolDefinition:
    """发送给模型的协议无关工具定义。"""

    name: str
    description: str
    input_schema: dict
    category: str
    read_only: bool
    destructive: bool
    is_concurrency_safe: bool


@dataclass
class ToolCall:
    """模型请求 Dragon Code 执行的一次工具调用。"""

    id: str
    name: str
    arguments: dict | None
    raw_arguments: str = ""
    parse_error: str = ""


@dataclass
class ToolResult:
    """一次工具执行的结构化结果。"""

    call_id: str
    tool_name: str
    success: bool
    content: str = ""
    error_code: str = ""
    error_message: str = ""
    metadata: dict = field(default_factory=dict)
    truncated: bool = False

    def to_model_text(self) -> str:
        """转成清晰的 JSON 文本回灌给模型。"""

        data = {
            "success": self.success,
            "content": self.content,
            "error": (
                {"code": self.error_code, "message": self.error_message}
                if self.error_code
                else None
            ),
            "metadata": self.metadata,
            "truncated": self.truncated,
        }
        return json.dumps(data, ensure_ascii=False)


@dataclass
class ChatMessage:
    """一条协议无关的文本、工具调用或工具结果消息。"""

    role: str
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    hidden_blocks: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class SystemPrompt:
    """一次请求使用的稳定提示和动态环境信息。"""

    stable: str
    environment: str


@dataclass
class LLMRequest:
    """Agent 发送给 LLM Client 的协议无关请求。"""

    messages: list[ChatMessage]
    tools: list[ToolDefinition]
    system: SystemPrompt
    reminder: str | None = None


@dataclass
class TokenUsage:
    """一次模型请求或一个 Agent 任务的 Token 用量。"""

    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0

    def add(self, other: TokenUsage) -> TokenUsage:
        """合并用量；只要其中一方未知，累计值也保持未知。"""

        input_tokens = None
        if self.input_tokens is not None and other.input_tokens is not None:
            input_tokens = self.input_tokens + other.input_tokens

        output_tokens = None
        if self.output_tokens is not None and other.output_tokens is not None:
            output_tokens = self.output_tokens + other.output_tokens

        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
        )

    @property
    def total_tokens(self) -> int | None:
        """输入和输出都已知时返回总数。"""

        if self.input_tokens is None or self.output_tokens is None:
            return None
        return self.input_tokens + self.output_tokens


@dataclass
class LLMEvent:
    """LLM Client 发送给 Agent 的统一流式事件。"""

    type: str
    text: str = ""
    tool_call: ToolCall | None = None
    message: ChatMessage | None = None
    usage: TokenUsage | None = None


@dataclass
class AgentEvent:
    """Agent 发送给 TUI 的协议无关事件。"""

    type: str
    text: str = ""
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None
    usage: TokenUsage | None = None
    iteration: int = 0
    max_iterations: int = 0
    error: Exception | None = None
    permission_request: PermissionRequest | None = None
