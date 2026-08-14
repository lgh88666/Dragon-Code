"""执行 Shell、Prompt、HTTP 和 Subagent 四类 Hook 动作。"""

from __future__ import annotations

import asyncio
import json
import os
import signal
from collections.abc import Callable

import httpx

from dragon_code.hooks.models import (
    BLOCKING_EVENTS,
    HookActionType,
    HookContext,
    HookDefinition,
    HookExecution,
)
from dragon_code.hooks.template import HookTemplateError, context_json, render_template

OUTPUT_LIMIT = 4_000
SAFE_ENV_NAMES = {
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "COMSPEC",
    "TEMP",
    "TMP",
    "HOME",
    "USERPROFILE",
    "LANG",
    "LC_ALL",
    "VIRTUAL_ENV",
}


def _shorten(text: str) -> str:
    if len(text) <= OUTPUT_LIMIT:
        return text
    return text[:OUTPUT_LIMIT] + "\n[truncated]"


async def _stop_process_tree(process: asyncio.subprocess.Process) -> None:
    """取消 Hook 时尽量连同 Shell 创建的子进程一起清理。"""

    if process.returncode is not None:
        return
    if os.name == "nt":
        try:
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(process.pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await killer.wait()
        except OSError:
            process.kill()
    else:
        try:
            # Unix 下 Hook 使用独立进程组，超时或取消时连同子进程一起结束。
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.returncode is None:
        try:
            await process.wait()
        except ProcessLookupError:
            pass


class HookActionExecutor:
    """四类动作共用的错误包装入口。"""

    def __init__(self, reminder_sink: Callable[[str], None] | None = None):
        self.reminder_sink = reminder_sink or (lambda _text: None)

    async def execute(self, hook: HookDefinition, context: HookContext) -> HookExecution:
        try:
            return await asyncio.wait_for(
                self._execute(hook, context),
                timeout=hook.timeout,
            )
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            return HookExecution(hook.name, hook.action.type, "timeout", "Hook 执行超时。")
        except HookTemplateError as error:
            return HookExecution(hook.name, hook.action.type, "failed", str(error))
        except Exception:
            # 外部动作异常不可破坏 Agent Loop，也不向界面暴露堆栈或秘密。
            return HookExecution(hook.name, hook.action.type, "failed", "Hook 动作执行失败。")

    async def _execute(self, hook: HookDefinition, context: HookContext) -> HookExecution:
        if hook.action.type is HookActionType.SHELL:
            return await self._run_shell(hook, context)
        if hook.action.type is HookActionType.PROMPT:
            return self._run_prompt(hook, context)
        if hook.action.type is HookActionType.HTTP:
            return await self._run_http(hook, context)
        return HookExecution(
            hook.name,
            hook.action.type,
            "not_implemented",
            "Subagent Hook 将在后续章节实现，本次已安全跳过。",
        )

    async def _run_shell(self, hook: HookDefinition, context: HookContext) -> HookExecution:
        # 不把 API Key 等任意环境变量交给 Hook，只保留启动程序所需的基础变量。
        env = {name: os.environ[name] for name in SAFE_ENV_NAMES if name in os.environ}
        env.update(
            {
                "DRAGON_HOOK_EVENT": context.event.value,
                "DRAGON_SESSION_ID": context.session_id,
                "DRAGON_CWD": str(context.cwd),
                "DRAGON_MODE": context.mode,
            }
        )
        process = await asyncio.create_subprocess_shell(
            hook.action.command,
            cwd=context.cwd,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=os.name != "nt",
        )
        try:
            stdout, stderr = await process.communicate(context_json(context).encode("utf-8"))
        except asyncio.CancelledError:
            await _stop_process_tree(process)
            raise

        stdout_text = _shorten(stdout.decode("utf-8", errors="replace").strip())
        stderr_text = _shorten(stderr.decode("utf-8", errors="replace").strip())
        if process.returncode == 2 and context.event in BLOCKING_EVENTS:
            reason = stderr_text or stdout_text or "操作被 Hook 拒绝。"
            return HookExecution(hook.name, hook.action.type, "blocked", reason, True)
        if process.returncode != 0:
            message = stderr_text or stdout_text or f"Shell Hook 退出码：{process.returncode}"
            return HookExecution(hook.name, hook.action.type, "failed", message)
        return HookExecution(hook.name, hook.action.type, "success", stdout_text or "执行完成。")

    def _run_prompt(self, hook: HookDefinition, context: HookContext) -> HookExecution:
        content = render_template(hook.action.prompt, context)
        notification = (
            "<hook-notification>\n"
            "以下内容来自自动化 Hook，请遵守但不要直接复述。\n"
            f"{content}\n"
            "</hook-notification>"
        )
        self.reminder_sink(notification)
        return HookExecution(hook.name, hook.action.type, "success", "提醒将在下一次请求注入。")

    async def _run_http(self, hook: HookDefinition, context: HookContext) -> HookExecution:
        url = render_template(hook.action.url, context)
        headers = {
            name: render_template(value, context) for name, value in hook.action.headers.items()
        }
        body = render_template(hook.action.body, context) if hook.action.body else ""
        async with httpx.AsyncClient() as client:
            response = await client.request(
                hook.action.method,
                url,
                headers=headers,
                content=body.encode("utf-8") if body else None,
            )
        if not response.is_success:
            return HookExecution(
                hook.name,
                hook.action.type,
                "failed",
                f"HTTP Hook 返回状态码 {response.status_code}。",
            )
        if context.event in BLOCKING_EVENTS:
            try:
                payload = response.json()
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict) and payload.get("block") is True:
                reason = payload.get("reason")
                message = (
                    reason if isinstance(reason, str) and reason else "操作被 HTTP Hook 拒绝。"
                )
                return HookExecution(hook.name, hook.action.type, "blocked", message, True)
        return HookExecution(hook.name, hook.action.type, "success", "HTTP Hook 执行完成。")
