"""MCP 两层配置、校验和环境变量展开测试。"""

from pathlib import Path

import pytest

from dragon_code.mcp import load_mcp_config


def write_yaml(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_files_return_empty_config(tmp_path: Path):
    config = load_mcp_config(tmp_path / "project.yaml", tmp_path / "user.yaml")

    assert config.servers == {}
    assert config.warnings == []


def test_project_server_fully_overrides_user_server(tmp_path: Path):
    user = write_yaml(
        tmp_path / "user.yaml",
        """
mcp_servers:
  shared:
    type: stdio
    command: user-command
    args: [user]
  user-only:
    type: stdio
    command: user-only-command
""",
    )
    project = write_yaml(
        tmp_path / "project.yaml",
        """
mcp_servers:
  shared:
    type: http
    url: https://example.com/mcp
  project-only:
    type: stdio
    command: project-command
""",
    )

    config = load_mcp_config(project, user)

    assert list(config.servers) == ["shared", "user-only", "project-only"]
    assert config.servers["shared"].transport == "http"
    assert config.servers["shared"].command == ""
    assert config.servers["shared"].url == "https://example.com/mcp"


def test_expands_only_env_and_headers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MCP_TOKEN", "secret-value")
    project = write_yaml(
        tmp_path / "project.yaml",
        """
mcp_servers:
  local:
    type: stdio
    command: "${MCP_TOKEN}"
    args: ["${MCP_TOKEN}"]
    env:
      TOKEN: "Bearer ${MCP_TOKEN}"
  remote:
    type: http
    url: "https://example.com/${MCP_TOKEN}"
    headers:
      Authorization: "Bearer ${MCP_TOKEN}"
""",
    )

    config = load_mcp_config(project, tmp_path / "missing-user.yaml")

    assert config.servers["local"].command == "${MCP_TOKEN}"
    assert config.servers["local"].args == ["${MCP_TOKEN}"]
    assert config.servers["local"].env == {"TOKEN": "Bearer secret-value"}
    assert config.servers["remote"].url == "https://example.com/${MCP_TOKEN}"
    assert config.servers["remote"].headers == {"Authorization": "Bearer secret-value"}


def test_missing_variable_skips_only_affected_server(tmp_path: Path):
    project = write_yaml(
        tmp_path / "project.yaml",
        """
mcp_servers:
  missing-secret:
    type: http
    url: https://example.com/mcp
    headers:
      Authorization: "Bearer ${DRAGON_TEST_MISSING_TOKEN}"
  healthy:
    type: stdio
    command: python
""",
    )

    config = load_mcp_config(project, tmp_path / "missing-user.yaml")

    assert list(config.servers) == ["healthy"]
    assert "DRAGON_TEST_MISSING_TOKEN" in config.warnings[0]
    assert "Bearer" not in config.warnings[0]


@pytest.mark.parametrize(
    ("server_yaml", "message"),
    [
        ("type: other", "type 只支持"),
        ("type: stdio", "command"),
        ("type: http", "url"),
        ("type: stdio\ncommand: python\nargs: wrong", "args"),
        ("type: stdio\ncommand: python\nenv: wrong", "env"),
        ("type: http\nurl: https://example.com\nheaders: wrong", "headers"),
    ],
)
def test_invalid_server_is_skipped(tmp_path: Path, server_yaml: str, message: str):
    indented = "\n".join(f"    {line}" for line in server_yaml.splitlines())
    project = write_yaml(
        tmp_path / "project.yaml",
        f"mcp_servers:\n  broken:\n{indented}\n",
    )

    config = load_mcp_config(project, tmp_path / "missing-user.yaml")

    assert config.servers == {}
    assert message in config.warnings[0]


def test_invalid_user_yaml_does_not_block_project(tmp_path: Path):
    user = write_yaml(tmp_path / "user.yaml", "mcp_servers: [")
    project = write_yaml(
        tmp_path / "project.yaml",
        """
mcp_servers:
  healthy:
    type: stdio
    command: python
""",
    )

    config = load_mcp_config(project, user)

    assert list(config.servers) == ["healthy"]
    assert "YAML 格式错误" in config.warnings[0]
