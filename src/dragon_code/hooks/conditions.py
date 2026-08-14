"""固定且安全的 Hook 条件语法。"""

from __future__ import annotations

import json
import re

from dragon_code.hooks.models import Condition, ConditionGroup, HookContext
from dragon_code.matching import MatcherKind, compile_matcher, match_value

FIELD_PATTERN = r"[A-Za-z_][A-Za-z0-9_.]*"
QUOTED_PATTERN = r'"((?:[^"\\]|\\.)*)"'
EXACT_RE = re.compile(rf"^({FIELD_PATTERN})\s*(==|!=)\s*{QUOTED_PATTERN}$")
GLOB_RE = re.compile(rf"^({FIELD_PATTERN})\s+glob\s+{QUOTED_PATTERN}$")
REGEX_RE = re.compile(rf"^({FIELD_PATTERN})\s*=~\s*/((?:[^/\\]|\\.)*)/$")


def _unescape_quoted(value: str) -> str:
    return json.loads(f'"{value}"')


def parse_condition(expression: str) -> Condition:
    """解析一个简单表达式，不执行任何 Python 代码。"""

    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("Hook 条件必须是非空字符串。")
    text = expression.strip()

    match = EXACT_RE.fullmatch(text)
    if match:
        field, operator, value = match.groups()
        kind = MatcherKind.EXACT if operator == "==" else MatcherKind.NOT
        return Condition(field, compile_matcher(kind, _unescape_quoted(value)))

    match = GLOB_RE.fullmatch(text)
    if match:
        field, value = match.groups()
        return Condition(field, compile_matcher(MatcherKind.GLOB, _unescape_quoted(value)))

    match = REGEX_RE.fullmatch(text)
    if match:
        field, pattern = match.groups()
        return Condition(field, compile_matcher(MatcherKind.REGEX, pattern))

    raise ValueError("Hook 条件格式不受支持。")


def parse_condition_group(raw: object) -> ConditionGroup | None:
    """解析单条件或一层 all_of/any_of 条件组。"""

    if raw is None:
        return None
    if isinstance(raw, str):
        return ConditionGroup("all_of", (parse_condition(raw),))
    if not isinstance(raw, dict):
        raise ValueError("Hook 的 if 必须是字符串或条件组。")

    keys = set(raw)
    if keys not in ({"all_of"}, {"any_of"}):
        raise ValueError("条件组只能选择 all_of 或 any_of，且不能混用。")
    mode = next(iter(keys))
    items = raw[mode]
    if not isinstance(items, list) or not items:
        raise ValueError(f"{mode} 必须包含至少一个条件。")
    if any(not isinstance(item, str) for item in items):
        raise ValueError("本章不支持嵌套条件组。")
    return ConditionGroup(mode, tuple(parse_condition(item) for item in items))


def condition_matches(group: ConditionGroup | None, context: HookContext) -> bool:
    if group is None:
        return True
    results = []
    for condition in group.conditions:
        value = context.get(condition.field)
        path_mode = condition.field.endswith("path") or ".path" in condition.field
        results.append(match_value(condition.matcher, value, path_mode=path_mode))
    return all(results) if group.mode == "all_of" else any(results)
