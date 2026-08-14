"""解析目录型 Skill 的 tool.json。"""

import json
import re
from pathlib import Path
from typing import Any

from dragon_code.skills.parser import SkillParseError, SkillPathArgument, SkillToolSpec

MAX_TOOL_JSON_BYTES = 128 * 1024
TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > MAX_TOOL_JSON_BYTES:
            raise SkillParseError(f"tool.json 超过 {MAX_TOOL_JSON_BYTES // 1024}KB：{path}")
        raw = json.loads(path.read_text(encoding="utf-8"))
    except SkillParseError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SkillParseError(f"tool.json 不是有效 JSON：{path}") from error
    if not isinstance(raw, dict):
        raise SkillParseError(f"tool.json 根节点必须是对象：{path}")
    return raw


def _path_arguments(raw: Any, path: Path) -> tuple[SkillPathArgument, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise SkillParseError(f"security.pathArguments 必须是列表：{path}")
    result = []
    for item in raw:
        if not isinstance(item, dict):
            raise SkillParseError(f"pathArguments 每项必须是对象：{path}")
        name = item.get("name")
        access = item.get("access")
        if not isinstance(name, str) or not name or access not in {"read", "write"}:
            raise SkillParseError(f"pathArguments 需要 name 和 read/write access：{path}")
        result.append(SkillPathArgument(name=name, access=access))
    return tuple(result)


def _string_list(raw: Any, field: str, path: Path) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or any(not isinstance(item, str) or not item for item in raw):
        raise SkillParseError(f"{field} 必须是非空字符串列表：{path}")
    return tuple(raw)


def _resolve_script(skill_dir: Path, raw: Any, path: Path) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise SkillParseError(f"自定义工具缺少 script：{path}")
    script = (skill_dir / raw).resolve(strict=False)
    root = skill_dir.resolve(strict=True)
    try:
        script.relative_to(root)
    except ValueError as error:
        raise SkillParseError(f"工具脚本不能逃出 Skill 目录：{path}") from error
    if not script.is_file():
        raise SkillParseError(f"工具脚本不存在：{script}")
    if script.suffix.lower() != ".py":
        raise SkillParseError(f"ch11 只支持 Python 工具脚本：{script}")
    return script


def load_tool_specs(skill_name: str, skill_dir: Path) -> tuple[SkillToolSpec, ...]:
    """读取一个目录型 Skill 的可选 tool.json。"""

    path = skill_dir / "tool.json"
    if not path.exists():
        return ()
    root = _read_json(path)
    tools = root.get("tools")
    if not isinstance(tools, list):
        raise SkillParseError(f"tool.json 的 tools 必须是列表：{path}")

    result = []
    seen = set()
    for item in tools:
        if not isinstance(item, dict):
            raise SkillParseError(f"tools 每项必须是对象：{path}")
        local_name = item.get("name")
        description = item.get("description")
        schema = item.get("inputSchema")
        if not isinstance(local_name, str) or not TOOL_NAME_PATTERN.fullmatch(local_name):
            raise SkillParseError(f"自定义工具名称不合法：{path}")
        if not isinstance(description, str) or not description.strip():
            raise SkillParseError(f"自定义工具缺少 description：{path}")
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise SkillParseError(f"自定义工具 inputSchema 必须是 object Schema：{path}")

        global_name = f"skill__{skill_name.replace('-', '_')}__{local_name}"
        if global_name in seen:
            raise SkillParseError(f"自定义工具名称重复：{global_name}")
        seen.add(global_name)

        annotations = item.get("annotations") or {}
        if not isinstance(annotations, dict):
            raise SkillParseError(f"annotations 必须是对象：{path}")
        read_only = annotations.get("readOnlyHint") is True
        destructive_raw = annotations.get("destructiveHint")
        destructive = destructive_raw is not False

        security = item.get("security") or {}
        if not isinstance(security, dict):
            raise SkillParseError(f"security 必须是对象：{path}")
        result.append(
            SkillToolSpec(
                name=global_name,
                description=description.strip(),
                input_schema=schema,
                script_path=_resolve_script(skill_dir, item.get("script"), path),
                read_only=read_only,
                destructive=destructive,
                command_arguments=_string_list(
                    security.get("commandArguments"), "security.commandArguments", path
                ),
                path_arguments=_path_arguments(security.get("pathArguments"), path),
            )
        )
    return tuple(result)
