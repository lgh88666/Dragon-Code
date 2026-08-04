"""根据 Provider 配置创建 LLM Client。"""

from dragon_code.clients.anthropic import AnthropicClient
from dragon_code.clients.base import LLMClient
from dragon_code.clients.openai import OpenAIClient
from dragon_code.models import ProviderConfig


def create_llm_client(config: ProviderConfig) -> LLMClient:
    """按 Provider 的协议名称创建对应客户端。"""

    if config.protocol == "anthropic":
        return AnthropicClient(config)
    if config.protocol == "openai":
        return OpenAIClient(config)
    raise ValueError(f"不支持的 Provider 协议：{config.protocol}")
