"""项目各模块共享的简单数据模型。"""

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
class ChatMessage:
    """一条用户或助手消息。"""

    role: str
    content: str


@dataclass
class TurnEvent:
    """ChatSession 发送给 TUI 的事件。"""

    type: str
    text: str = ""
    error: Exception | None = None
