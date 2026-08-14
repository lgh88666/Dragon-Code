"""模型自动加载 Skill 与执行 Skill 自定义 Python 工具。"""

import asyncio
import json
import sys
from typing import Any

from pydantic import BaseModel, Field

from dragon_code.models import ToolCall, ToolDefinition, ToolResult
from dragon_code.skills.manager import SkillManager, SkillRuntime
from dragon_code.skills.parser import SkillToolSpec
from dragon_code.tools.base import Tool
from dragon_code.tools.registry import ToolRegistry

MAX_SCRIPT_OUTPUT_BYTES = 100 * 1024


class LoadSkillArguments(BaseModel):
    name: str = Field(description="要激活的 Skill 名称，必须来自可用 Skill 列表。")


class LoadSkillTool(Tool):
    """让模型根据用户意图激活一份完整 SOP。"""

    name = "LoadSkill"
    description = (
        "按名称激活一个可用 Skill。先根据系统提示中的 Skill 名称和描述判断是否匹配，"
        "只有用户任务明显符合时才调用。成功后下一轮会收到完整 SOP，不要重复调用。"
    )
    category = "system"
    read_only = True
    destructive = False
    is_concurrency_safe = True
    is_system_tool = True
    arguments_model = LoadSkillArguments

    def __init__(self, manager: SkillManager, runtime: SkillRuntime) -> None:
        self.manager = manager
        self.runtime = runtime

    async def run(self, call: ToolCall, arguments: LoadSkillArguments) -> ToolResult:
        skill, issue = self.manager.refresh_one(arguments.name)
        if skill is None:
            return self._failure(call, "unknown_skill", f"未知 Skill：{arguments.name}")
        self.runtime.activate(skill)
        content = f"已激活 Skill：{skill.name}。下一轮请遵循该 Skill 的完整指令。"
        if issue is not None:
            content += " 最新文件无效，已使用上一次有效版本。"
        return self._success(call, content, metadata={"skill": skill.name, "mode": skill.mode})


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "null":
        return value is None
    return True


def _validate_arguments(arguments: dict[str, Any], schema: dict[str, Any]) -> str | None:
    required = schema.get("required", [])
    if isinstance(required, list):
        for name in required:
            if isinstance(name, str) and name not in arguments:
                return f"缺少必需参数：{name}"

    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return "inputSchema.properties 必须是对象。"
    for name, value in arguments.items():
        definition = properties.get(name)
        if not isinstance(definition, dict):
            continue
        expected = definition.get("type")
        if isinstance(expected, str) and not _matches_type(value, expected):
            return f"参数 {name} 的类型应为 {expected}。"
    return None


async def _read_limited(stream: asyncio.StreamReader | None) -> tuple[bytes, bool]:
    if stream is None:
        return b"", False
    kept = bytearray()
    truncated = False
    while True:
        chunk = await stream.read(8192)
        if not chunk:
            break
        remaining = MAX_SCRIPT_OUTPUT_BYTES - len(kept)
        if remaining > 0:
            kept.extend(chunk[:remaining])
        if len(chunk) > remaining:
            truncated = True
    return bytes(kept), truncated


class SkillScriptTool(Tool):
    """通过独立 Python 子进程执行目录型 Skill 工具。"""

    category = "command"
    is_concurrency_safe = False

    def __init__(self, spec: SkillToolSpec, *, timeout_seconds: float = 30.0) -> None:
        self.spec = spec
        self.name = spec.name
        self.description = spec.description
        self.read_only = spec.read_only
        self.destructive = spec.destructive
        self.timeout_seconds = timeout_seconds
        self.permission_command_arguments = spec.command_arguments
        self.permission_path_arguments = tuple(
            (item.name, item.access) for item in spec.path_arguments
        )

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self.spec.input_schema,
            category=self.category,
            read_only=self.read_only,
            destructive=self.destructive,
            is_concurrency_safe=False,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        if call.arguments is None:
            return self._failure(
                call, "invalid_json", call.parse_error or "工具参数不是有效 JSON。"
            )
        validation_error = _validate_arguments(call.arguments, self.spec.input_schema)
        if validation_error:
            return self._failure(call, "invalid_arguments", validation_error)
        try:
            return await asyncio.wait_for(self._execute_process(call), self.timeout_seconds)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            return self._failure(call, "timeout", f"工具执行超过 {self.timeout_seconds:g} 秒。")
        except OSError:
            return self._failure(call, "start_failed", "无法启动 Skill 工具脚本。")

    async def _execute_process(self, call: ToolCall) -> ToolResult:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(self.spec.script_path),
            cwd=self.spec.script_path.parent,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            assert process.stdin is not None
            process.stdin.write(json.dumps(call.arguments, ensure_ascii=False).encode("utf-8"))
            await process.stdin.drain()
            process.stdin.close()
            stdout_task = asyncio.create_task(_read_limited(process.stdout))
            stderr_task = asyncio.create_task(_read_limited(process.stderr))
            stdout_value, stderr_value, _return_code = await asyncio.gather(
                stdout_task,
                stderr_task,
                process.wait(),
            )
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise

        stdout, stdout_truncated = stdout_value
        stderr, stderr_truncated = stderr_value
        if process.returncode != 0:
            # 脚本错误输出可能含有令牌或环境变量，不能直接回传给模型和界面。
            message = f"Skill 工具脚本执行失败，退出码为 {process.returncode}。"
            return self._failure(call, "nonzero_exit", message)
        if stdout_truncated:
            return self._failure(call, "output_too_large", "脚本标准输出超过 100KB。")

        try:
            payload = json.loads(stdout.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            return self._failure(call, "invalid_output", "脚本没有返回有效 JSON。")
        if not isinstance(payload, dict):
            return self._failure(call, "invalid_output", "脚本结果必须是 JSON 对象。")
        if payload.get("success") is False:
            error = payload.get("error")
            if not isinstance(error, dict):
                return self._failure(call, "script_error", "脚本报告执行失败。")
            code = error.get("code") if isinstance(error.get("code"), str) else "script_error"
            message = (
                error.get("message")
                if isinstance(error.get("message"), str)
                else "脚本报告执行失败。"
            )
            return self._failure(call, code, message)

        content = payload.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        metadata = payload.get("metadata")
        return self._success(
            call,
            content,
            metadata=metadata if isinstance(metadata, dict) else {},
            truncated=stderr_truncated,
        )


def registry_for_skill_tools(skills) -> ToolRegistry:
    """把当前快照中的自定义工具适配为独立 Registry。"""

    registry = ToolRegistry()
    for skill in skills:
        for spec in skill.custom_tools:
            registry.register(SkillScriptTool(spec))
    return registry
