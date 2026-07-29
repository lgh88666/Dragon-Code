"""根据配置创建模型 Provider。"""

from dragon_code.models import ProviderConfig
from dragon_code.providers.anthropic import AnthropicProvider
from dragon_code.providers.base import BaseProvider
from dragon_code.providers.openai import OpenAIProvider


def create_provider(config: ProviderConfig) -> BaseProvider:
    """按协议名称创建对应的 Provider。"""

    if config.protocol == "anthropic":
        return AnthropicProvider(config)
    if config.protocol == "openai":
        return OpenAIProvider(config)
    raise ValueError(f"不支持的 Provider 协议：{config.protocol}")
