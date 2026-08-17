"""解析 Agent 角色的 YAML frontmatter 和 Markdown 正文。"""

import re
from pathlib import Path
from typing import Any

import yaml

from dragon_code.permissions import PermissionMode
from dragon_code.subagents.models import AgentDefinition, AgentDefinitionSource

MAX_AGENT_BYTES = 256 * 1024
AGENT_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DEFAULT_SUBAGENT_MODEL = "deepseek-v4-flash"
DEFAULT_MAX_ITERATIONS = 50


class AgentDefinitionError(ValueError):
    """Agent 定义格式错误。"""


def _read_limited(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_AGENT_BYTES:
            raise AgentDefinitionError(f"Agent 定义超过 256KB：{path}")
        return path.read_text(encoding="utf-8")
    except AgentDefinitionError:
        raise
    except (OSError, UnicodeError) as error:
        raise AgentDefinitionError(f"无法读取 UTF-8 Agent 定义：{path}") from error


def _split_frontmatter(text: str, path: Path) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise AgentDefinitionError(f"Agent 定义缺少 YAML frontmatter：{path}")
    closing = -1
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing = index
            break
    if closing < 0:
        raise AgentDefinitionError(f"Agent 定义 frontmatter 没有结束标记：{path}")
    try:
        raw = yaml.safe_load("\n".join(lines[1:closing]))
    except yaml.YAMLError as error:
        raise AgentDefinitionError(f"Agent 定义 YAML 格式错误：{path}") from error
    if not isinstance(raw, dict):
        raise AgentDefinitionError(f"Agent 定义 frontmatter 必须是对象：{path}")
    body = "\n".join(lines[closing + 1 :]).strip()
    if not body:
        raise AgentDefinitionError(f"Agent 定义正文不能为空：{path}")
    return raw, body


def _required_text(raw: dict[str, Any], field: str, path: Path) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AgentDefinitionError(f"Agent 定义缺少有效的 {field}：{path}")
    return value.strip()


def _tool_names(raw: dict[str, Any], field: str, path: Path) -> tuple[str, ...]:
    value = raw.get(field, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise AgentDefinitionError(f"{field} 必须是字符串列表：{path}")
    result = tuple(item.strip() for item in value if item.strip())
    if len(result) != len(set(result)):
        raise AgentDefinitionError(f"{field} 不能包含重复工具：{path}")
    return result


def parse_agent_definition(
    path: Path,
    source: AgentDefinitionSource,
) -> AgentDefinition:
    """读取并校验一份 Agent Markdown 定义。"""

    resolved = path.resolve(strict=False)
    raw, body = _split_frontmatter(_read_limited(resolved), resolved)
    name = _required_text(raw, "name", resolved)
    description = _required_text(raw, "description", resolved)
    if not AGENT_NAME_PATTERN.fullmatch(name):
        raise AgentDefinitionError(f"Agent 名称只能包含小写字母、数字和连字符：{resolved}")

    model = raw.get("model", DEFAULT_SUBAGENT_MODEL)
    if not isinstance(model, str) or not model.strip():
        raise AgentDefinitionError(f"model 必须是非空字符串：{resolved}")

    max_iterations = raw.get("maxTurns", DEFAULT_MAX_ITERATIONS)
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int):
        raise AgentDefinitionError(f"maxTurns 必须是整数：{resolved}")
    if not 1 <= max_iterations <= 200:
        raise AgentDefinitionError(f"maxTurns 必须在 1 到 200 之间：{resolved}")

    mode_value = raw.get("permissionMode", PermissionMode.DEFAULT.value)
    try:
        permission_mode = PermissionMode(mode_value)
    except (TypeError, ValueError) as error:
        raise AgentDefinitionError(f"permissionMode 不受支持：{resolved}") from error

    background = raw.get("background", False)
    if not isinstance(background, bool):
        raise AgentDefinitionError(f"background 必须是布尔值：{resolved}")

    return AgentDefinition(
        name=name,
        description=description,
        system_prompt=body,
        allowed_tools=_tool_names(raw, "tools", resolved),
        disallowed_tools=_tool_names(raw, "disallowedTools", resolved),
        model=model.strip(),
        max_iterations=max_iterations,
        permission_mode=permission_mode,
        background=background,
        source=source,
        source_path=resolved,
    )
