"""Hook 上下文脱敏、JSON 传递和安全模板渲染。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from dragon_code.hooks.models import HookContext

TEMPLATE_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\}\}")
SENSITIVE_NAMES = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "access_token",
    "refresh_token",
    "token",
}
NORMALIZED_SENSITIVE_NAMES = {re.sub(r"[^a-z0-9]", "", item) for item in SENSITIVE_NAMES}
SENSITIVE_SUFFIXES = ("apikey", "accesstoken", "refreshtoken", "password", "secret")


class HookTemplateError(ValueError):
    """模板引用了无效字段。"""


def _safe_value(value: object, key: str = "") -> object:
    normalized_key = re.sub(r"[^a-z0-9]", "", key.casefold())
    if normalized_key in NORMALIZED_SENSITIVE_NAMES or normalized_key.endswith(SENSITIVE_SUFFIXES):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): _safe_value(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_safe_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def safe_context(context: HookContext) -> dict[str, object]:
    """生成可发送给 Hook 动作的脱敏上下文。"""

    data = {
        **context.data,
        "event": context.event.value,
        "session_id": context.session_id,
        "cwd": str(context.cwd),
        "mode": context.mode,
    }
    return _safe_value(data)  # type: ignore[return-value]


def context_json(context: HookContext) -> str:
    return json.dumps(safe_context(context), ensure_ascii=False, default=str)


def render_template(template: str, context: HookContext) -> str:
    """只替换明确的 `{{field.path}}`，缺失字段直接报告失败。"""

    values = safe_context(context)

    def replace(match: re.Match[str]) -> str:
        current: object = values
        field_path = match.group(1)
        for part in field_path.split("."):
            if not isinstance(current, dict) or part not in current:
                raise HookTemplateError(f"Hook 模板字段不存在：{field_path}")
            current = current[part]
        if isinstance(current, dict | list):
            return json.dumps(current, ensure_ascii=False)
        return "" if current is None else str(current)

    return TEMPLATE_PATTERN.sub(replace, template)
