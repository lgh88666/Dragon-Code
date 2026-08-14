"""权限规则解析、匹配、三级加载和永久保存。"""

import os
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml

from dragon_code.models import ToolCall
from dragon_code.permissions.models import (
    PermissionDecision,
    PermissionMode,
    PermissionResult,
    PermissionRule,
    RuleLayer,
)

TOOL_NAMES = {"Bash", "Read", "Write", "Edit", "Glob", "Grep"}
FILE_TOOLS = {"Read", "Write", "Edit", "Glob", "Grep"}
SPECIAL_PATTERN_CHARS = {"*", "?", "[", "]", "\\"}
MCP_TOOL_NAME_PATTERN = re.compile(r"^mcp__[A-Za-z0-9_-]+__[A-Za-z0-9_-]+$")
SKILL_TOOL_NAME_PATTERN = re.compile(r"^skill__[A-Za-z0-9_-]+__[A-Za-z0-9_-]+$")


class RuleParseError(ValueError):
    """单条权限规则格式不正确。"""


def parse_rule(raw: str, decision: PermissionDecision) -> PermissionRule:
    """把 Tool 或 Tool(pattern) 文本解析为权限规则。"""

    if not isinstance(raw, str) or not raw.strip():
        raise RuleParseError("权限规则必须是非空字符串。")

    text = raw.strip()
    tool_name = text
    pattern: str | None = None

    if "(" in text:
        open_index = text.find("(")
        if not text.endswith(")"):
            raise RuleParseError("带参数的权限规则必须以右括号结束。")
        tool_name = text[:open_index].strip()
        pattern = text[open_index + 1 : -1]
        if not pattern:
            raise RuleParseError("权限规则的匹配模式不能为空。")

    if not is_supported_tool_name(tool_name):
        raise RuleParseError(f"未知工具规则：{tool_name}")
    if (is_mcp_tool_name(tool_name) or is_skill_tool_name(tool_name)) and pattern is not None:
        raise RuleParseError("外部工具权限规则只支持完整工具名，不支持参数模式。")

    return PermissionRule(
        tool_name=tool_name,
        pattern=pattern,
        decision=decision,
        raw=text,
    )


def is_mcp_tool_name(tool_name: str) -> bool:
    """判断是否为带完整 Server 命名空间的 MCP 工具。"""

    return MCP_TOOL_NAME_PATTERN.fullmatch(tool_name) is not None


def is_skill_tool_name(tool_name: str) -> bool:
    """判断是否为 Skill 自定义工具的完整命名空间。"""

    return SKILL_TOOL_NAME_PATTERN.fullmatch(tool_name) is not None


def is_supported_tool_name(tool_name: str) -> bool:
    return tool_name in TOOL_NAMES or is_mcp_tool_name(tool_name) or is_skill_tool_name(tool_name)


def _escape_exact(value: str) -> str:
    """转义规则通配符，让永久授权只匹配当前值。"""

    escaped = []
    for character in value:
        if character in SPECIAL_PATTERN_CHARS:
            escaped.append("\\")
        escaped.append(character)
    return "".join(escaped)


def _relative_path(project_root: Path, raw_path: str) -> str:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = project_root / candidate
    resolved = candidate.resolve(strict=False)
    try:
        return resolved.relative_to(project_root.resolve()).as_posix()
    except ValueError as error:
        raise RuleParseError("无法为项目外路径生成永久授权。") from error


def make_exact_rule(call: ToolCall, project_root: Path) -> str:
    """根据当前调用生成不会自动泛化的精确 allow 规则。"""

    if call.arguments is None:
        raise RuleParseError("工具参数不是有效对象。")

    if call.name == "Bash":
        value = call.arguments.get("command")
    elif call.name in {"Read", "Write", "Edit"}:
        raw_path = call.arguments.get("path")
        value = _relative_path(project_root, raw_path) if isinstance(raw_path, str) else None
    elif call.name == "Grep":
        raw_path = call.arguments.get("path", ".")
        value = _relative_path(project_root, raw_path) if isinstance(raw_path, str) else None
    elif call.name == "Glob":
        value = call.arguments.get("pattern")
    elif is_mcp_tool_name(call.name) or is_skill_tool_name(call.name):
        # 外部工具参数 Schema 不固定，永久权限按完整工具名保存。
        return call.name
    else:
        raise RuleParseError(f"无法为未知工具生成权限规则：{call.name}")

    if not isinstance(value, str) or not value:
        raise RuleParseError("工具缺少生成精确规则所需的参数。")
    return f"{call.name}({_escape_exact(value)})"


def _pattern_to_regex(pattern: str, *, path_mode: bool) -> re.Pattern[str]:
    """把简单 glob 转换为完整匹配的正则表达式。"""

    parts = ["^"]
    index = 0
    while index < len(pattern):
        character = pattern[index]
        if character == "\\" and index + 1 < len(pattern):
            index += 1
            parts.append(re.escape(pattern[index]))
        elif character == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                index += 1
                parts.append(".*")
            else:
                parts.append("[^/]*" if path_mode else ".*")
        elif character == "?":
            parts.append("[^/]" if path_mode else ".")
        else:
            parts.append(re.escape(character))
        index += 1
    parts.append("$")
    return re.compile("".join(parts), re.IGNORECASE if os.name == "nt" and path_mode else 0)


def _match_value(call: ToolCall, project_root: Path) -> tuple[str, bool] | None:
    if call.arguments is None:
        return None

    if call.name == "Bash":
        command = call.arguments.get("command")
        return (command, False) if isinstance(command, str) else None

    if call.name in {"Read", "Write", "Edit"}:
        raw_path = call.arguments.get("path")
    elif call.name == "Grep":
        raw_path = call.arguments.get("path", ".")
    elif call.name == "Glob":
        pattern = call.arguments.get("pattern")
        if not isinstance(pattern, str):
            return None
        return pattern.replace("\\", "/"), True
    else:
        return None

    if not isinstance(raw_path, str):
        return None
    try:
        return _relative_path(project_root, raw_path), True
    except RuleParseError:
        return None


def rule_matches(rule: PermissionRule, call: ToolCall, project_root: Path) -> bool:
    """判断一条已解析规则是否匹配当前工具调用。"""

    if rule.tool_name != call.name:
        return False
    if rule.pattern is None:
        return True

    match_value = _match_value(call, project_root)
    if match_value is None:
        return False
    value, path_mode = match_value
    return _pattern_to_regex(rule.pattern, path_mode=path_mode).fullmatch(value) is not None


def _mode(value: Any) -> PermissionMode | None:
    try:
        return PermissionMode(value)
    except (TypeError, ValueError):
        return None


def _parse_rule_list(raw: Any, decision: PermissionDecision) -> list[PermissionRule]:
    if not isinstance(raw, list):
        return []

    rules = []
    for item in raw:
        try:
            rules.append(parse_rule(item, decision))
        except (RuleParseError, TypeError):
            # 单条规则有问题时只跳过这一条，其他合法规则继续生效。
            continue
    return rules


def _load_layer(name: str, path: Path) -> RuleLayer:
    try:
        text = path.read_text(encoding="utf-8")
        raw = yaml.safe_load(text)
    except (OSError, yaml.YAMLError):
        return RuleLayer(name=name, path=path)

    if not isinstance(raw, dict):
        return RuleLayer(name=name, path=path)
    permissions = raw.get("permissions")
    if not isinstance(permissions, dict):
        return RuleLayer(name=name, path=path)

    return RuleLayer(
        name=name,
        path=path,
        allow=_parse_rule_list(permissions.get("allow"), PermissionDecision.ALLOW),
        deny=_parse_rule_list(permissions.get("deny"), PermissionDecision.DENY),
        default_mode=_mode(permissions.get("mode")),
    )


class RuleStore:
    """保存本地、项目和用户三级权限规则。"""

    def __init__(self, project_root: Path, layers: list[RuleLayer]):
        self.project_root = project_root.resolve()
        self.layers = layers

    @classmethod
    def empty(cls, project_root: Path) -> "RuleStore":
        """创建不读取磁盘的空规则仓库，主要用于测试和显式注入。"""

        root = project_root.resolve()
        settings_dir = root / ".dragon-code"
        layers = [
            RuleLayer("local", settings_dir / "settings.local.yaml"),
            RuleLayer("project", settings_dir / "settings.yaml"),
            RuleLayer("user", settings_dir / "unused-user-settings.yaml"),
        ]
        return cls(root, layers)

    @classmethod
    def load(cls, project_root: Path, *, user_home: Path | None = None) -> "RuleStore":
        root = project_root.resolve()
        home = (user_home or Path.home()).resolve()
        layers = [
            _load_layer("local", root / ".dragon-code" / "settings.local.yaml"),
            _load_layer("project", root / ".dragon-code" / "settings.yaml"),
            _load_layer("user", home / ".dragon-code" / "settings.yaml"),
        ]
        return cls(root, layers)

    def match(self, call: ToolCall) -> PermissionResult | None:
        """按层级与层内 deny 优先级查找第一项明确规则。"""

        for layer in self.layers:
            for rule in layer.deny:
                if rule_matches(rule, call, self.project_root):
                    return PermissionResult(
                        PermissionDecision.DENY,
                        f"{layer.name}_rule",
                        f"调用被 {layer.name} 级 deny 规则拒绝。",
                        rule.raw,
                    )
            for rule in layer.allow:
                if rule_matches(rule, call, self.project_root):
                    return PermissionResult(
                        PermissionDecision.ALLOW,
                        f"{layer.name}_rule",
                        f"调用被 {layer.name} 级 allow 规则允许。",
                        rule.raw,
                    )
        return None

    def default_mode(self) -> PermissionMode:
        for layer in self.layers:
            if layer.default_mode is not None:
                return layer.default_mode
        return PermissionMode.DEFAULT

    def save_local_allow(self, exact_rule: str) -> None:
        """原子保存一条本地精确 allow 规则，并同步内存规则。"""

        parsed_rule = parse_rule(exact_rule, PermissionDecision.ALLOW)
        local = self.layers[0]
        if any(rule.raw == parsed_rule.raw for rule in local.allow):
            return

        raw: dict[str, Any] = {}
        if local.path.exists():
            try:
                loaded = yaml.safe_load(local.path.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError):
                loaded = None
            if isinstance(loaded, dict):
                raw = loaded

        permissions = raw.get("permissions")
        if not isinstance(permissions, dict):
            permissions = {}
            raw["permissions"] = permissions
        allow = permissions.get("allow")
        if not isinstance(allow, list):
            allow = []
            permissions["allow"] = allow
        if exact_rule not in allow:
            allow.append(exact_rule)

        local.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=local.path.parent,
                delete=False,
                prefix="settings.",
                suffix=".tmp",
            ) as temporary:
                yaml.safe_dump(raw, temporary, allow_unicode=True, sort_keys=False)
                temporary_path = Path(temporary.name)
            temporary_path.replace(local.path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

        local.allow.append(parsed_rule)
