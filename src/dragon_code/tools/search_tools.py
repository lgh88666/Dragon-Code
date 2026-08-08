"""按路径模式查找文件，以及按正则搜索文本内容。"""

import asyncio
import re
from pathlib import Path

from pydantic import BaseModel, Field

from dragon_code.models import ToolCall, ToolResult
from dragon_code.tools.base import Tool, ToolExecutionError
from dragon_code.tools.path_utils import resolve_workspace_path, validate_glob_pattern

MAX_MATCH_LINE = 500
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache"}


class GlobArguments(BaseModel):
    pattern: str = Field(description="工作目录内的 glob 模式，例如 **/*.py。")


class GrepArguments(BaseModel):
    pattern: str = Field(description="要搜索的 Python 正则表达式。")
    path: str = Field(default=".", description="工作目录内的文件或子目录，默认为整个目录。")


class SearchTool(Tool):
    def __init__(self, workdir: Path):
        self.workdir = workdir.resolve()


class GlobTool(SearchTool):
    name = "Glob"
    description = "按 glob 模式查找工作目录内的文件，返回排序后的相对路径。"
    category = "search"
    read_only = True
    destructive = False
    is_concurrency_safe = True
    arguments_model = GlobArguments

    async def run(self, call: ToolCall, arguments: GlobArguments) -> ToolResult:
        return await asyncio.to_thread(self._glob, call, arguments)

    def _glob(self, call: ToolCall, arguments: GlobArguments) -> ToolResult:
        validate_glob_pattern(arguments.pattern)
        matches = []
        for path in self.workdir.glob(arguments.pattern):
            resolved = path.resolve(strict=False)
            try:
                relative = resolved.relative_to(self.workdir)
            except ValueError:
                continue
            if resolved.is_file():
                matches.append(relative.as_posix())
        matches.sort()
        return self._success(
            call,
            "\n".join(matches),
            metadata={"matches": len(matches)},
        )


class GrepTool(SearchTool):
    name = "Grep"
    description = (
        "使用正则表达式搜索工作目录内的 UTF-8 文件，返回文件、行号和命中行。查找文件名请使用 Glob。"
    )
    category = "search"
    read_only = True
    destructive = False
    is_concurrency_safe = True
    arguments_model = GrepArguments

    async def run(self, call: ToolCall, arguments: GrepArguments) -> ToolResult:
        return await asyncio.to_thread(self._grep, call, arguments)

    def _grep(self, call: ToolCall, arguments: GrepArguments) -> ToolResult:
        try:
            regex = re.compile(arguments.pattern)
        except re.error as error:
            raise ToolExecutionError("invalid_pattern", f"正则表达式无效：{error}") from error

        root = resolve_workspace_path(self.workdir, arguments.path)
        if not root.exists():
            raise ToolExecutionError("not_found", "搜索范围不存在。")
        files = [root] if root.is_file() else root.rglob("*")
        matches: list[str] = []
        total = 0
        for path in files:
            if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for line_number, line in enumerate(lines, 1):
                if regex.search(line):
                    total += 1
                    relative = path.relative_to(self.workdir).as_posix()
                    matches.append(f"{relative}:{line_number}: {line[:MAX_MATCH_LINE]}")
        return self._success(
            call,
            "\n".join(matches),
            metadata={"matches": total},
        )
