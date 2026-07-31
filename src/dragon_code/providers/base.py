"""Provider 的公共基类和安全错误。"""

import asyncio

from dragon_code.models import ChatMessage, ProviderConfig, ProviderEvent, ToolDefinition


class ProviderError(Exception):
    """可以安全展示在终端界面中的模型调用错误。"""

    def __init__(self, category: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.category = category
        self.message = message
        self.retryable = retryable


class BaseProvider:
    """Anthropic 和 OpenAI Provider 共用的简单基类。"""

    def __init__(self, config: ProviderConfig):
        self.config = config

    @property
    def name(self) -> str:
        """返回界面显示名称。"""

        return self.config.name

    @property
    def model(self) -> str:
        """返回模型名称。"""

        return self.config.model

    async def stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str,
        tools: list[ToolDefinition],
    ):
        """流式返回正文、工具调用、Token 用量和完整消息事件。"""

        raise NotImplementedError
        yield ProviderEvent(type="completed")  # pragma: no cover


def make_provider_error(error: Exception) -> ProviderError:
    """把 SDK 异常转换成不泄露密钥的公开错误。"""

    if isinstance(error, asyncio.CancelledError):
        raise error

    class_name = type(error).__name__.lower()
    status_code = getattr(error, "status_code", None)

    if status_code in {401, 403} or "authentication" in class_name or "permission" in class_name:
        return ProviderError("authentication", "模型服务鉴权失败，请检查 API Key。")
    if status_code == 429 or "ratelimit" in class_name or "rate_limit" in class_name:
        return ProviderError("rate_limit", "请求过于频繁，请稍后再试。", retryable=True)
    if status_code == 404 or "notfound" in class_name or "not_found" in class_name:
        return ProviderError("not_found", "模型或接口地址不存在，请检查配置。")
    if status_code in {400, 422} or "badrequest" in class_name or "invalid" in class_name:
        return ProviderError("invalid_request", "模型请求参数无效，请检查配置。")
    if "connection" in class_name or "timeout" in class_name or isinstance(error, OSError):
        return ProviderError("network", "无法连接模型服务，请检查网络。", retryable=True)

    # 未知异常不使用原始文本，避免 SDK 请求信息或密钥被带到界面。
    return ProviderError("unknown", "模型服务发生未知错误，请稍后再试。")
