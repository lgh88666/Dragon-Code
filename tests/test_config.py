"""配置加载测试。"""

from pathlib import Path

import pytest

from dragon_code.config import ConfigError, load_config


def write_config(path: Path, text: str) -> Path:
    """写入测试专用配置。"""

    path.write_text(text, encoding="utf-8")
    return path


def test_load_single_provider(tmp_path: Path):
    path = write_config(
        tmp_path / "config.yaml",
        """
providers:
  - name: Test Anthropic
    protocol: anthropic
    api_key: secret-value
    model: test-model
    thinking: true
""",
    )

    config = load_config(str(path))

    assert len(config.providers) == 1
    assert config.providers[0].protocol == "anthropic"
    assert config.providers[0].thinking is True
    assert config.providers[0].context_window == 200_000
    assert config.providers[0].summary_model is None
    assert "secret-value" not in repr(config.providers[0])


def test_load_multiple_providers(tmp_path: Path):
    path = write_config(
        tmp_path / "config.yaml",
        """
providers:
  - name: One
    protocol: anthropic
    api_key: key-one
    model: model-one
  - name: Two
    protocol: openai
    api_key: key-two
    model: model-two
    base_url: https://example.com/v1
""",
    )

    config = load_config(str(path))

    assert len(config.providers) == 2
    assert config.providers[1].base_url == "https://example.com/v1"
    assert config.providers[1].context_window == 128_000


def test_provider_context_window_and_summary_model(tmp_path: Path):
    path = write_config(
        tmp_path / "config.yaml",
        """
providers:
  - name: DeepSeek
    protocol: openai
    api_key: secret-value
    model: deepseek-v4-pro
    context_window: 256000
    summary_model: deepseek-v4-flash
""",
    )

    provider = load_config(str(path)).providers[0]

    assert provider.context_window == 256_000
    assert provider.summary_model == "deepseek-v4-flash"


@pytest.mark.parametrize("yaml_value", ["0", "-1", "true", "1.5", "'128000'"])
def test_invalid_context_window(tmp_path: Path, yaml_value: str):
    path = write_config(
        tmp_path / "config.yaml",
        "\n".join(
            [
                "providers:",
                "  - name: Demo",
                "    protocol: openai",
                "    api_key: k",
                "    model: m",
                f"    context_window: {yaml_value}",
            ]
        ),
    )

    with pytest.raises(ConfigError, match=r"providers\[0\]\.context_window"):
        load_config(str(path))


@pytest.mark.parametrize("value", ["''", "'   '", "[]", "false"])
def test_invalid_summary_model(tmp_path: Path, value: str):
    path = write_config(
        tmp_path / "config.yaml",
        "\n".join(
            [
                "providers:",
                "  - name: Demo",
                "    protocol: openai",
                "    api_key: k",
                "    model: m",
                f"    summary_model: {value}",
            ]
        ),
    )

    with pytest.raises(ConfigError, match=r"providers\[0\]\.summary_model"):
        load_config(str(path))


@pytest.mark.parametrize(
    ("yaml_text", "expected"),
    [
        ("providers: []", "providers 必须是非空列表"),
        ("providers:\n  - wrong", "providers[0] 必须是对象"),
        (
            "providers:\n  - name: Demo\n    protocol: openai\n    model: m",
            "providers[0].api_key",
        ),
        (
            "providers:\n  - name: Demo\n    protocol: other\n    api_key: k\n    model: m",
            "providers[0].protocol",
        ),
        (
            "providers:\n  - name: Demo\n    protocol: openai\n    api_key: k\n"
            '    model: m\n    thinking: "yes"',
            "providers[0].thinking",
        ),
    ],
)
def test_invalid_config(tmp_path: Path, yaml_text: str, expected: str):
    path = write_config(tmp_path / "config.yaml", yaml_text)

    with pytest.raises(ConfigError, match=expected.replace("[", r"\[").replace("]", r"\]")):
        load_config(str(path))


def test_missing_file(tmp_path: Path):
    with pytest.raises(ConfigError, match="配置文件不存在"):
        load_config(str(tmp_path / "missing.yaml"))


def test_invalid_yaml(tmp_path: Path):
    path = write_config(tmp_path / "config.yaml", "providers: [")

    with pytest.raises(ConfigError, match="YAML 格式错误"):
        load_config(str(path))
