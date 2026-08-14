"""Hook 与权限规则共用的字符串匹配能力。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import StrEnum


class MatcherKind(StrEnum):
    """支持的四种匹配方式。"""

    EXACT = "exact"
    NOT = "not"
    REGEX = "regex"
    GLOB = "glob"


@dataclass(frozen=True)
class Matcher:
    """一条已经校验完成的匹配规则。"""

    kind: MatcherKind
    pattern: str
    compiled: re.Pattern[str] | None = field(default=None, repr=False, compare=False)

    def matches(self, value: str, *, path_mode: bool = False) -> bool:
        return match_value(self, value, path_mode=path_mode)


def _glob_to_regex(pattern: str, *, path_mode: bool) -> str:
    """把项目旧有的简单 glob 语义转换为完整匹配正则。"""

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
    return "".join(parts)


def compile_matcher(kind: MatcherKind | str, pattern: str) -> Matcher:
    """创建 Matcher；非法正则在配置加载期直接报错。"""

    matcher_kind = MatcherKind(kind)
    if not isinstance(pattern, str):
        raise ValueError("匹配模式必须是字符串。")
    try:
        compiled = re.compile(pattern) if matcher_kind is MatcherKind.REGEX else None
    except re.error as error:
        raise ValueError(f"非法正则表达式：{error}") from error
    return Matcher(matcher_kind, pattern, compiled)


def match_value(matcher: Matcher, value: object, *, path_mode: bool = False) -> bool:
    """匹配任意上下文字段；非字符串值转成稳定文本。"""

    if value is None:
        return False
    text = str(value).lower() if isinstance(value, bool) else str(value)
    ignore_case = path_mode and os.name == "nt"

    if matcher.kind is MatcherKind.EXACT:
        return (
            text.casefold() == matcher.pattern.casefold()
            if ignore_case
            else text == matcher.pattern
        )
    if matcher.kind is MatcherKind.NOT:
        return (
            text.casefold() != matcher.pattern.casefold()
            if ignore_case
            else text != matcher.pattern
        )
    if matcher.kind is MatcherKind.REGEX:
        if ignore_case:
            return re.search(matcher.pattern, text, flags=re.IGNORECASE) is not None
        compiled = matcher.compiled or re.compile(matcher.pattern)
        return compiled.search(text) is not None

    flags = re.IGNORECASE if ignore_case else 0
    pattern = _glob_to_regex(matcher.pattern, path_mode=path_mode)
    return re.fullmatch(pattern, text, flags=flags) is not None
