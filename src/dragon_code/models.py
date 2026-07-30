"""项目各模块共享的简单数据模型。"""

import json
from dataclasses import dataclass, field


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


@dataclass
class ProviderEvent:
    """Provider 发送给 ChatSession 的统一流式事件。"""

    type: str
    text: str = ""
    tool_call: ToolCall | None = None
    message: ChatMessage | None = None


@dataclass
class TurnEvent:
    """ChatSession 发送给 TUI 的事件。"""

    type: str
    text: str = ""
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None
    error: Exception | None = None
