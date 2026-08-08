"""在当前操作系统的默认 shell 中异步执行命令。"""

import asyncio
from pathlib import Path

from pydantic import BaseModel, Field

from dragon_code.models import ToolCall, ToolResult
from dragon_code.tools.base import Tool


class BashArguments(BaseModel):
    command: str = Field(
        description="确实需要系统 shell 时执行的完整命令；不要用它替代专用文件工具。"
    )


class BashTool(Tool):
    name = "Bash"
    description = (
        "在 Dragon Code 启动目录使用系统默认 shell 执行命令。"
        "读取文件优先使用 Read，查找文件优先使用 Glob，搜索内容优先使用 Grep。"
        "不要用 shell 拼凑专用工具已经能完成的操作。"
        "返回 stdout、stderr 和退出码；命令可能修改系统，应谨慎使用。"
    )
    category = "command"
    read_only = False
    destructive = True
    is_concurrency_safe = False
    arguments_model = BashArguments

    def __init__(self, workdir: Path):
        self.workdir = workdir.resolve()

    async def run(self, call: ToolCall, arguments: BashArguments) -> ToolResult:
        process = await asyncio.create_subprocess_shell(
            arguments.command,
            cwd=self.workdir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await process.communicate()
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        metadata = {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": process.returncode,
        }
        content = f"stdout:\n{stdout}\nstderr:\n{stderr}\nexit_code: {process.returncode}"
        if process.returncode == 0:
            return self._success(call, content, metadata=metadata)
        return ToolResult(
            call_id=call.id,
            tool_name=self.name,
            success=False,
            content=content,
            error_code="nonzero_exit",
            error_message=f"命令退出码为 {process.returncode}。",
            metadata=metadata,
        )
