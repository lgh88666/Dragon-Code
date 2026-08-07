"""读取并校验用户级、项目级 MCP Server 配置。"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

VARIABLE_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass
class McpServerConfig:
    """一个已经完成校验和变量展开的 MCP Server。"""

    name: str
    transport: Literal["stdio", "http"]
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class McpConfig:
    """两层配置合并后的 MCP 配置与可展示警告。"""

    servers: dict[str, McpServerConfig] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _read_server_map(path: Path, layer: str, warnings: list[str]) -> dict[str, Any]:
    """读取一层 mcp_servers；文件缺失视为空配置。"""

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError:
        warnings.append(f"{layer} MCP 配置无法读取，已跳过：{path}")
        return {}

    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError:
        warnings.append(f"{layer} MCP 配置 YAML 格式错误，已跳过：{path}")
        return {}

    if not isinstance(raw, dict):
        warnings.append(f"{layer} MCP 配置根节点不是对象，已跳过：{path}")
        return {}

    servers = raw.get("mcp_servers")
    if servers is None:
        return {}
    if not isinstance(servers, dict):
        warnings.append(f"{layer} mcp_servers 必须是对象，已跳过该层。")
        return {}
    return servers


def _string_map(value: Any, field_name: str) -> tuple[dict[str, str] | None, str]:
    if value is None:
        return {}, ""
    if not isinstance(value, dict):
        return None, f"{field_name} 必须是字符串对象"
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            return None, f"{field_name} 的键和值必须是字符串"
        result[key] = item
    return result, ""


def _expand_map(
    values: dict[str, str],
) -> tuple[dict[str, str] | None, list[str]]:
    """展开一组字符串；任一变量缺失时让调用方跳过整个 Server。"""

    missing: set[str] = set()
    for value in values.values():
        for variable in VARIABLE_PATTERN.findall(value):
            if variable not in os.environ:
                missing.add(variable)
    if missing:
        return None, sorted(missing)

    expanded = {
        key: VARIABLE_PATTERN.sub(lambda match: os.environ[match.group(1)], value)
        for key, value in values.items()
    }
    return expanded, []


def _parse_server(name: Any, raw: Any) -> tuple[McpServerConfig | None, str]:
    """把一项原始配置转成 ServerConfig，失败时返回可读原因。"""

    if not isinstance(name, str) or not name.strip():
        return None, "Server 名必须是非空字符串"
    if not isinstance(raw, dict):
        return None, "Server 配置必须是对象"

    transport = raw.get("type")
    if transport not in {"stdio", "http"}:
        return None, "type 只支持 stdio 或 http"

    if transport == "stdio":
        command = raw.get("command")
        if not isinstance(command, str) or not command.strip():
            return None, "stdio Server 缺少非空 command"

        args = raw.get("args", [])
        if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
            return None, "args 必须是字符串数组"

        env, error = _string_map(raw.get("env"), "env")
        if env is None:
            return None, error
        expanded_env, missing = _expand_map(env)
        if expanded_env is None:
            return None, f"缺少环境变量：{', '.join(missing)}"

        return (
            McpServerConfig(
                name=name.strip(),
                transport="stdio",
                command=command.strip(),
                args=list(args),
                env=expanded_env,
            ),
            "",
        )

    url = raw.get("url")
    if not isinstance(url, str) or not url.strip():
        return None, "http Server 缺少非空 url"

    headers, error = _string_map(raw.get("headers"), "headers")
    if headers is None:
        return None, error
    expanded_headers, missing = _expand_map(headers)
    if expanded_headers is None:
        return None, f"缺少环境变量：{', '.join(missing)}"

    return (
        McpServerConfig(
            name=name.strip(),
            transport="http",
            url=url.strip(),
            headers=expanded_headers,
        ),
        "",
    )


def load_mcp_config(
    project_config_path: Path,
    user_config_path: Path | None = None,
) -> McpConfig:
    """加载两层配置；项目级同名 Server 完整覆盖用户级。"""

    warnings: list[str] = []
    if user_config_path is None:
        try:
            user_config_path = Path.home() / ".dragon-code" / "config.yaml"
        except RuntimeError:
            user_config_path = None
            warnings.append("无法确定用户目录，已跳过用户级 MCP 配置。")

    user_servers = (
        _read_server_map(user_config_path, "用户级", warnings)
        if user_config_path is not None
        else {}
    )
    project_servers = _read_server_map(project_config_path, "项目级", warnings)

    merged = dict(user_servers)
    merged.update(project_servers)

    servers: dict[str, McpServerConfig] = {}
    for name, raw in merged.items():
        parsed, error = _parse_server(name, raw)
        if parsed is None:
            warnings.append(f"MCP Server {name!s} 已跳过：{error}。")
            continue
        servers[parsed.name] = parsed

    return McpConfig(servers=servers, warnings=warnings)
