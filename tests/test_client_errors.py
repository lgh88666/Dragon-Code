"""LLM Client 公开错误和密钥脱敏测试。"""

import pytest

from dragon_code.clients.anthropic import AnthropicClient
from dragon_code.clients.base import LLMClient, make_llm_error
from dragon_code.clients.factory import create_llm_client
from dragon_code.clients.openai import OpenAIClient
from dragon_code.models import ProviderConfig


class FakeStatusError(Exception):
    def __init__(self, status_code: int, message: str = ""):
        super().__init__(message)
        self.status_code = status_code


@pytest.mark.parametrize(
    ("status", "category", "retryable"),
    [
        (401, "authentication", False),
        (429, "rate_limit", True),
        (404, "not_found", False),
        (400, "invalid_request", False),
    ],
)
def test_status_error_mapping(status: int, category: str, retryable: bool):
    error = make_llm_error(FakeStatusError(status))

    assert error.category == category
    assert error.retryable is retryable


def test_network_error_mapping():
    error = make_llm_error(ConnectionError("network down"))

    assert error.category == "network"
    assert error.retryable is True


def test_unknown_error_does_not_leak_secret():
    secret = "dragon-secret-key"
    error = make_llm_error(RuntimeError(f"request Authorization: Bearer {secret}"))

    assert error.category == "unknown"
    assert secret not in str(error)


def test_provider_config_repr_hides_api_key():
    config = ProviderConfig("Demo", "openai", "hidden-key", "test-model")
    client = LLMClient(config)

    assert client.name == "Demo"
    assert client.model == "test-model"
    assert "hidden-key" not in repr(config)


def test_factory_selects_client():
    anthropic_client = create_llm_client(
        ProviderConfig("Claude", "anthropic", "key", "claude-test")
    )
    openai_client = create_llm_client(ProviderConfig("OpenAI", "openai", "key", "gpt-test"))

    assert isinstance(anthropic_client, AnthropicClient)
    assert isinstance(openai_client, OpenAIClient)


def test_factory_rejects_unknown_protocol():
    config = ProviderConfig("Unknown", "other", "key", "model")

    with pytest.raises(ValueError, match="不支持的 Provider 协议"):
        create_llm_client(config)
