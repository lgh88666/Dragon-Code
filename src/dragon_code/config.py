"""读取和校验 Dragon Code 的 YAML 配置。"""

from pathlib import Path
from typing import Any

import yaml

from dragon_code.models import AppConfig, ProviderConfig


class ConfigError(Exception):
    """配置文件不符合要求时抛出的可读错误。"""


def _require_text(item: dict[str, Any], field_name: str, location: str) -> str:
    """读取一个必填字符串，并生成包含字段位置的错误。"""

    value = item.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{location}.{field_name} 必须是非空字符串")
    return value.strip()


def _parse_provider(raw: Any, index: int) -> ProviderConfig:
    """把一项 YAML 数据转换为 ProviderConfig。"""

    location = f"providers[{index}]"
    if not isinstance(raw, dict):
        raise ConfigError(f"{location} 必须是对象")

    name = _require_text(raw, "name", location)
    protocol = _require_text(raw, "protocol", location).lower()
    api_key = _require_text(raw, "api_key", location)
    model = _require_text(raw, "model", location)

    if protocol not in {"anthropic", "openai"}:
        raise ConfigError(f"{location}.protocol 只支持 anthropic 或 openai")

    base_url = raw.get("base_url")
    if base_url is not None and (not isinstance(base_url, str) or not base_url.strip()):
        raise ConfigError(f"{location}.base_url 必须是非空字符串或省略")

    thinking = raw.get("thinking", False)
    if not isinstance(thinking, bool):
        raise ConfigError(f"{location}.thinking 必须是 true 或 false")

    return ProviderConfig(
        name=name,
        protocol=protocol,
        api_key=api_key,
        model=model,
        base_url=base_url.strip() if isinstance(base_url, str) else None,
        thinking=thinking,
    )


def load_config(path: str) -> AppConfig:
    """读取指定 YAML 文件，并返回经过完整校验的配置。"""

    config_path = Path(path)
    try:
        text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise ConfigError(f"配置文件不存在：{path}") from error
    except OSError as error:
        raise ConfigError(f"无法读取配置文件：{path}") from error

    try:
        raw_config = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ConfigError(f"配置文件 YAML 格式错误：{path}") from error

    if not isinstance(raw_config, dict):
        raise ConfigError("配置文件根节点必须是对象")

    providers = raw_config.get("providers")
    if not isinstance(providers, list) or not providers:
        raise ConfigError("providers 必须是非空列表")

    parsed = [_parse_provider(item, index) for index, item in enumerate(providers)]
    return AppConfig(providers=parsed)
