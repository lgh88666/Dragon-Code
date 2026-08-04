"""连续发送两次相同稳定前缀，观察模型端点的缓存用量。"""

import argparse
import asyncio
from pathlib import Path

from dragon_code import __version__
from dragon_code.clients.base import LLMClient, LLMError
from dragon_code.clients.factory import create_llm_client
from dragon_code.config import ConfigError, load_config
from dragon_code.models import ChatMessage, LLMRequest, SystemPrompt, TokenUsage
from dragon_code.prompt import build_system_prompt
from dragon_code.tools import create_default_registry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="发送两次安全测试请求，打印输入、输出和缓存 Token 用量。"
    )
    parser.add_argument(
        "--config",
        default=".dragon-code/config.yaml",
        help="配置文件路径，默认 .dragon-code/config.yaml",
    )
    parser.add_argument(
        "--provider",
        help="按配置中的 provider name 选择；省略时使用第一项",
    )
    parser.add_argument(
        "--cache-tag",
        help="仅用于验证首次写入的固定标记；两次请求会使用相同标记",
    )
    return parser.parse_args()


def choose_provider(config_path: str, provider_name: str | None):
    """只返回经过校验的 ProviderConfig，不打印其中的密钥。"""

    providers = load_config(config_path).providers
    if provider_name is None:
        return providers[0]
    for provider in providers:
        if provider.name == provider_name:
            return provider
    raise ConfigError(f"配置中不存在名为 {provider_name!r} 的 provider")


async def collect_usage(client: LLMClient, request: LLMRequest) -> TokenUsage:
    """消费完整流，但只保留安全的用量数据。"""

    usage = TokenUsage()
    async for event in client.stream(request):
        if event.type == "usage" and event.usage is not None:
            usage = event.usage
    return usage


def format_usage(index: int, usage: TokenUsage) -> str:
    return (
        f"第 {index} 次：输入={usage.input_tokens}，输出={usage.output_tokens}，"
        f"缓存写入={usage.cache_write_tokens}，缓存读取={usage.cache_read_tokens}"
    )


async def run_smoke(
    config_path: str,
    provider_name: str | None,
    cache_tag: str | None,
) -> int:
    provider = choose_provider(config_path, provider_name)
    client = create_llm_client(provider)
    working_dir = Path.cwd()
    system = await build_system_prompt(working_dir, __version__, client.model)
    if cache_tag:
        # 只在烟测请求中添加固定标记，制造一个尚未写入过的新缓存前缀。
        system = SystemPrompt(
            stable=f"{system.stable}\n\n缓存烟测标记：{cache_tag}",
            environment=system.environment,
        )
    request = LLMRequest(
        messages=[ChatMessage("user", "请只回复 OK，不要调用工具。")],
        tools=create_default_registry(working_dir).definitions(),
        system=system,
    )

    usages = []
    for index in range(1, 3):
        usage = await collect_usage(client, request)
        usages.append(usage)
        print(format_usage(index, usage))

    if all(item.cache_write_tokens == 0 and item.cache_read_tokens == 0 for item in usages):
        print("未观察到缓存用量：端点可能不支持缓存字段，或稳定前缀未达到缓存门槛。")
    return 0


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(run_smoke(args.config, args.provider, args.cache_tag))
    except ConfigError as error:
        print(f"配置错误：{error}")
        return 1
    except LLMError as error:
        print(f"模型请求失败：{error.message}")
        return 1
    except Exception:
        # 不输出底层异常文本，避免其中包含请求头、路径或密钥。
        print("缓存烟测失败，请检查当前配置和网络连接。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
