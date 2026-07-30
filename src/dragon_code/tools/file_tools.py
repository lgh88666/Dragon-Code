"""读取、写入和精确修改文本文件。"""

import asyncio
from pathlib import Path

from pydantic import BaseModel, Field

from dragon_code.models import ToolCall, ToolResult
from dragon_code.tools.base import Tool, ToolExecutionError
from dragon_code.tools.path_utils import resolve_workspace_path

MAX_READ_LINES = 2000
MAX_READ_CHARS = 100_000


class ReadArguments(BaseModel):
    path: str = Field(description="要读取的文件路径，可使用工作目录内的相对路径。")


class WriteArguments(BaseModel):
    path: str = Field(description="要创建或覆盖的文件路径。")
    content: str = Field(description="要完整写入文件的文本内容。")


class EditArguments(BaseModel):
    path: str = Field(description="要修改的文本文件路径。")
    old_text: str = Field(description="文件中必须恰好出现一次的原文片段。")
    new_text: str = Field(description="用于替换原文片段的新文本。")


class WorkspaceTool(Tool):
    """需要固定工作目录的工具。"""

    def __init__(self, workdir: Path):
        self.workdir = workdir.resolve()


class ReadTool(WorkspaceTool):
    name = "Read"
    description = (
        "读取工作目录内的 UTF-8 文本文件并返回带行号内容。"
        "需要了解文件真实内容时使用；不要用于目录或二进制文件。"
    )
    category = "filesystem"
    read_only = True
    destructive = False
    is_concurrency_safe = True
    arguments_model = ReadArguments

    async def run(self, call: ToolCall, arguments: ReadArguments) -> ToolResult:
        return await asyncio.to_thread(self._read, call, arguments)

    def _read(self, call: ToolCall, arguments: ReadArguments) -> ToolResult:
        path = resolve_workspace_path(self.workdir, arguments.path)
        if not path.exists():
            raise ToolExecutionError("not_found", "文件不存在。")
        if not path.is_file():
            raise ToolExecutionError("not_file", "目标路径不是普通文件。")
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError as error:
            raise ToolExecutionError("encoding_error", "文件不是可读取的 UTF-8 文本。") from error

        selected = lines[:MAX_READ_LINES]
        numbered = "\n".join(f"{index:>4} | {line}" for index, line in enumerate(selected, 1))
        truncated = len(lines) > MAX_READ_LINES or len(numbered) > MAX_READ_CHARS
        if len(numbered) > MAX_READ_CHARS:
            numbered = numbered[:MAX_READ_CHARS]
        return self._success(
            call,
            numbered,
            metadata={"path": str(path.relative_to(self.workdir)), "line_count": len(lines)},
            truncated=truncated,
        )


class WriteTool(WorkspaceTool):
    name = "Write"
    description = (
        "创建或完整覆盖工作目录内的 UTF-8 文本文件，并自动创建父目录。"
        "只有确实需要替换整个文件时使用；局部修改优先使用 Edit。"
    )
    category = "filesystem"
    read_only = False
    destructive = True
    is_concurrency_safe = False
    arguments_model = WriteArguments

    async def run(self, call: ToolCall, arguments: WriteArguments) -> ToolResult:
        return await asyncio.to_thread(self._write, call, arguments)

    def _write(self, call: ToolCall, arguments: WriteArguments) -> ToolResult:
        path = resolve_workspace_path(self.workdir, arguments.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(arguments.content, encoding="utf-8")
        relative = str(path.relative_to(self.workdir))
        return self._success(
            call,
            f"已写入 {relative}",
            metadata={"path": relative, "characters": len(arguments.content)},
        )


class EditTool(WorkspaceTool):
    name = "Edit"
    description = (
        "在工作目录内的 UTF-8 文件中做一次原文精确替换。"
        "old_text 必须恰好匹配一次；零次或多次都会拒绝修改。"
    )
    category = "filesystem"
    read_only = False
    destructive = True
    is_concurrency_safe = False
    arguments_model = EditArguments

    async def run(self, call: ToolCall, arguments: EditArguments) -> ToolResult:
        return await asyncio.to_thread(self._edit, call, arguments)

    def _edit(self, call: ToolCall, arguments: EditArguments) -> ToolResult:
        path = resolve_workspace_path(self.workdir, arguments.path)
        if not path.is_file():
            raise ToolExecutionError("not_found", "要修改的文件不存在。")
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise ToolExecutionError("encoding_error", "文件不是可修改的 UTF-8 文本。") from error
        matches = content.count(arguments.old_text)
        if matches != 1:
            raise ToolExecutionError(
                "match_count",
                f"原文必须恰好匹配 1 次，实际匹配 {matches} 次。",
            )
        path.write_text(content.replace(arguments.old_text, arguments.new_text, 1), encoding="utf-8")
        relative = str(path.relative_to(self.workdir))
        return self._success(call, f"已修改 {relative}", metadata={"path": relative, "matches": 1})
