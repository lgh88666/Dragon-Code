"""解析 SKILL.md 的 YAML frontmatter 和 Markdown 正文。"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

MAX_SKILL_BYTES = 256 * 1024
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
VALID_MODES = {"inline", "fork"}
VALID_CONTEXTS = {"full", "recent", "none"}


class SkillParseError(ValueError):
    """Skill 文件格式错误。"""


@dataclass(frozen=True)
class SkillPathArgument:
    """自定义工具中需要路径沙箱检查的参数。"""

    name: str
    access: str


@dataclass(frozen=True)
class SkillToolSpec:
    """tool.json 解析后的单个自定义工具。"""

    name: str
    description: str
    input_schema: dict[str, Any]
    script_path: Path
    read_only: bool
    destructive: bool
    command_arguments: tuple[str, ...] = ()
    path_arguments: tuple[SkillPathArgument, ...] = ()

    @property
    def is_concurrency_safe(self) -> bool:
        # ch11 统一串行，风险注解不改变调度方式。
        return False


@dataclass(frozen=True)
class SkillDefinition:
    """一份已经通过校验的 Skill 定义。"""

    name: str
    description: str
    prompt_body: str
    allowed_tools: tuple[str, ...]
    mode: str
    model: str | None
    context: str
    source_level: str
    source_path: Path
    skill_dir: Path
    custom_tools: tuple[SkillToolSpec, ...] = ()


@dataclass(frozen=True)
class SkillLoadIssue:
    """加载单个 Skill 时可以安全展示的错误。"""

    source_path: Path
    code: str
    message: str


@dataclass(frozen=True)
class ActiveSkill:
    """当前会话中已经激活并完成参数替换的 Skill。"""

    name: str
    rendered_prompt: str
    allowed_tools: tuple[str, ...]


def _read_limited(path: Path, maximum: int) -> str:
    try:
        size = path.stat().st_size
    except OSError as error:
        raise SkillParseError(f"无法读取 Skill 文件：{path}") from error
    if size > maximum:
        raise SkillParseError(f"Skill 文件超过 {maximum // 1024}KB：{path}")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise SkillParseError(f"Skill 文件不是可读的 UTF-8 文本：{path}") from error


def _split_frontmatter(text: str, path: Path) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillParseError(f"SKILL.md 缺少 YAML frontmatter：{path}")

    closing_index = -1
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing_index = index
            break
    if closing_index < 0:
        raise SkillParseError(f"SKILL.md frontmatter 没有结束标记：{path}")

    try:
        raw = yaml.safe_load("\n".join(lines[1:closing_index]))
    except yaml.YAMLError as error:
        raise SkillParseError(f"SKILL.md YAML 格式错误：{path}") from error
    if not isinstance(raw, dict):
        raise SkillParseError(f"SKILL.md frontmatter 必须是对象：{path}")

    body = "\n".join(lines[closing_index + 1 :]).strip()
    if not body:
        raise SkillParseError(f"SKILL.md 正文不能为空：{path}")
    return raw, body


def _required_text(raw: dict[str, Any], field: str, path: Path) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise SkillParseError(f"SKILL.md 缺少有效的 {field}：{path}")
    return value.strip()


def _allowed_tools(raw: dict[str, Any], path: Path) -> tuple[str, ...]:
    value = raw.get("allowedTools", [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SkillParseError(f"allowedTools 必须是字符串列表：{path}")
    cleaned = tuple(item.strip() for item in value if item.strip())
    if len(cleaned) != len(set(cleaned)):
        raise SkillParseError(f"allowedTools 不能包含重复工具：{path}")
    return cleaned


def parse_skill_file(path: Path, source_level: str) -> SkillDefinition:
    """读取并解析一个 SKILL.md。"""

    resolved = path.resolve(strict=False)
    raw, body = _split_frontmatter(_read_limited(resolved, MAX_SKILL_BYTES), resolved)
    name = _required_text(raw, "name", resolved)
    description = _required_text(raw, "description", resolved)
    if not SKILL_NAME_PATTERN.fullmatch(name):
        raise SkillParseError(f"Skill 名称只能包含小写字母、数字和连字符：{resolved}")

    mode = raw.get("mode", "inline")
    if mode not in VALID_MODES:
        raise SkillParseError(f"Skill mode 只能是 inline 或 fork：{resolved}")
    context = raw.get("context", "recent" if mode == "fork" else "full")
    if context not in VALID_CONTEXTS:
        raise SkillParseError(f"Skill context 只能是 full、recent 或 none：{resolved}")

    model = raw.get("model")
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise SkillParseError(f"Skill model 必须是非空字符串：{resolved}")

    return SkillDefinition(
        name=name,
        description=description,
        prompt_body=body,
        allowed_tools=_allowed_tools(raw, resolved),
        mode=mode,
        model=model.strip() if isinstance(model, str) else None,
        context=context,
        source_level=source_level,
        source_path=resolved,
        skill_dir=resolved.parent,
    )


def render_skill_prompt(skill: SkillDefinition, arguments: str = "") -> str:
    """把命令后的自由文本替换进 Skill SOP。"""

    return skill.prompt_body.replace("$ARGUMENTS", arguments)
