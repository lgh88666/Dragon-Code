"""加载、校验并合并项目级和用户级 Hook 配置。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from dragon_code.hooks.conditions import parse_condition_group
from dragon_code.hooks.models import (
    BLOCKING_EVENTS,
    HookAction,
    HookActionType,
    HookDefinition,
    HookEvent,
    HookIssue,
    HookSnapshot,
)

DEFAULT_TIMEOUT = 10.0
MAX_TIMEOUT = 60.0


class HookLoader:
    """启动时读取一次 Hook；局部错误只跳过对应项目。"""

    def __init__(self, project_root: Path, *, user_home: Path | None = None):
        self.project_root = project_root.resolve()
        self.user_home = (user_home or Path.home()).resolve()

    def load(self) -> HookSnapshot:
        project_path = self.project_root / ".dragon-code" / "hooks.yaml"
        user_path = self.user_home / ".dragon-code" / "hooks.yaml"
        hooks: list[HookDefinition] = []
        issues: list[HookIssue] = []
        seen: set[str] = set()

        for source, path in (("project", project_path), ("user", user_path)):
            parsed, current_issues = self._load_file(path, source)
            issues.extend(current_issues)
            for hook in parsed:
                if hook.name in seen:
                    issues.append(
                        HookIssue(path, hook.name, "同名 Hook 已由项目级配置提供，当前项已跳过。")
                    )
                    continue
                seen.add(hook.name)
                hooks.append(hook)
        return HookSnapshot(tuple(hooks), tuple(issues))

    def _load_file(self, path: Path, source: str) -> tuple[list[HookDefinition], list[HookIssue]]:
        if not path.exists():
            return [], []
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except OSError:
            return [], [HookIssue(path, "", "无法读取 Hook 配置文件。")]
        except yaml.YAMLError:
            return [], [HookIssue(path, "", "Hook YAML 格式错误，无法解析。")]
        if not isinstance(raw, dict) or not isinstance(raw.get("hooks"), list):
            return [], [HookIssue(path, "", "Hook 配置顶层必须包含 hooks 列表。")]

        hooks = []
        issues = []
        local_names: set[str] = set()
        for item in raw["hooks"]:
            name = item.get("name", "") if isinstance(item, dict) else ""
            try:
                hook = self._parse_hook(item, source, path)
                if hook.name in local_names:
                    raise ValueError("同一文件中 Hook 名称重复。")
                local_names.add(hook.name)
                hooks.append(hook)
            except (TypeError, ValueError) as error:
                issues.append(HookIssue(path, str(name), str(error)))
        return hooks, issues

    @staticmethod
    def _parse_hook(raw: object, source: str, path: Path) -> HookDefinition:
        if not isinstance(raw, dict):
            raise ValueError("每条 Hook 必须是对象。")
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Hook 缺少有效名称。")
        try:
            event = HookEvent(raw.get("event"))
        except (TypeError, ValueError) as error:
            raise ValueError("Hook 事件未知或缺失。") from error
        action = _parse_action(raw.get("action"))
        condition = parse_condition_group(raw.get("if"))
        only_once = raw.get("only_once", False)
        run_async = raw.get("async", False)
        if not isinstance(only_once, bool) or not isinstance(run_async, bool):
            raise ValueError("only_once 和 async 必须是布尔值。")
        if run_async and event in BLOCKING_EVENTS:
            raise ValueError("可阻塞事件不允许 async: true。")
        timeout = raw.get("timeout", DEFAULT_TIMEOUT)
        if not isinstance(timeout, int | float) or isinstance(timeout, bool) or timeout <= 0:
            raise ValueError("timeout 必须是正数。")
        if timeout > MAX_TIMEOUT:
            raise ValueError(f"timeout 不能超过 {MAX_TIMEOUT:g} 秒。")
        return HookDefinition(
            name=name.strip(),
            event=event,
            condition=condition,
            action=action,
            only_once=only_once,
            run_async=run_async,
            timeout=float(timeout),
            source=source,
            source_path=path,
        )


def _string_map(raw: Any, field_name: str) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict) or any(
        not isinstance(k, str) or not isinstance(v, str) for k, v in raw.items()
    ):
        raise ValueError(f"{field_name} 必须是字符串映射。")
    return dict(raw)


def _parse_action(raw: object) -> HookAction:
    if not isinstance(raw, dict):
        raise ValueError("Hook 缺少 action 对象。")
    try:
        action_type = HookActionType(raw.get("type"))
    except (TypeError, ValueError) as error:
        raise ValueError("Hook 动作类型未知或缺失。") from error

    command = raw.get("command", "")
    prompt = raw.get("prompt", "")
    url = raw.get("url", "")
    body = raw.get("body", "")
    task = raw.get("task", "")
    for field_name, value in (
        ("command", command),
        ("prompt", prompt),
        ("url", url),
        ("body", body),
        ("task", task),
    ):
        if not isinstance(value, str):
            raise ValueError(f"动作字段 {field_name} 必须是字符串。")
    required = {
        HookActionType.SHELL: ("command", command),
        HookActionType.PROMPT: ("prompt", prompt),
        HookActionType.HTTP: ("url", url),
        HookActionType.SUBAGENT: ("task", task),
    }
    field_name, value = required[action_type]
    if not value.strip():
        raise ValueError(f"{action_type.value} 动作缺少 {field_name}。")
    method = raw.get("method", "POST")
    if not isinstance(method, str) or not method.strip():
        raise ValueError("HTTP method 必须是字符串。")
    return HookAction(
        type=action_type,
        command=command,
        prompt=prompt,
        url=url,
        method=method.upper(),
        headers=_string_map(raw.get("headers"), "headers"),
        body=body,
        task=task,
    )
