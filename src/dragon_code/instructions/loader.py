"""加载三层 DRAGON.md，并安全展开 @include。"""

from __future__ import annotations

import re
from pathlib import Path

MAX_INCLUDE_DEPTH = 5
_INCLUDE_RE = re.compile(r"^\s*@include\s+(.+?)\s*$")


class InstructionLoader:
    """加载项目级和用户级指令，失败时保留其余可用内容。"""

    def __init__(self, project_root: Path, user_home: Path | None = None):
        self.project_root = project_root.resolve()
        self.user_home = (user_home or Path.home()).resolve()
        self._warnings: list[str] = []

    def load(self) -> str:
        """按高优先级到低优先级加载三份 DRAGON.md。"""

        self._warnings = []
        user_config_root = (self.user_home / ".dragon-code").resolve()
        sources = [
            (self.project_root / "DRAGON.md", self.project_root),
            (self.project_root / ".dragon-code" / "DRAGON.md", self.project_root),
            (user_config_root / "DRAGON.md", user_config_root),
        ]

        sections: list[str] = []
        for path, boundary in sources:
            content = self._expand_file(path, boundary, 0, set()).strip()
            if content:
                sections.append(content)
        return "\n\n".join(sections)

    def warnings(self) -> list[str]:
        """返回本次加载产生的警告副本。"""

        return list(self._warnings)

    def _expand_file(
        self,
        path: Path,
        boundary: Path,
        depth: int,
        visited: set[Path],
    ) -> str:
        """递归展开一个文件；visited 只表示当前引用链。"""

        if depth > MAX_INCLUDE_DEPTH:
            self._warn(path, "超过最大嵌套深度 5，已跳过")
            return ""

        try:
            resolved_path = path.expanduser().resolve(strict=True)
            resolved_boundary = boundary.resolve(strict=True)
            resolved_path.relative_to(resolved_boundary)
        except FileNotFoundError:
            # 顶层文件缺失是正常情况，include 缺失才需要提示。
            if depth > 0:
                self._warn(path, "引用文件不存在，已跳过")
            return ""
        except (OSError, RuntimeError, ValueError):
            self._warn(path, "引用路径超出允许范围或无法解析，已跳过")
            return ""

        if resolved_path in visited:
            self._warn(resolved_path, "检测到循环引用，已跳过")
            return ""
        if not resolved_path.is_file():
            self._warn(resolved_path, "目标不是普通文件，已跳过")
            return ""

        try:
            raw = resolved_path.read_bytes()
        except OSError:
            self._warn(resolved_path, "文件不可读，已跳过")
            return ""
        if b"\x00" in raw[:512]:
            self._warn(resolved_path, "检测到二进制文件，已跳过")
            return ""
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            self._warn(resolved_path, "文件不是有效 UTF-8，已跳过")
            return ""

        visited.add(resolved_path)
        output: list[str] = []
        try:
            for line in text.splitlines():
                match = _INCLUDE_RE.fullmatch(line)
                if match is None:
                    output.append(line)
                    continue
                include_path = resolved_path.parent / match.group(1).strip()
                expanded = self._expand_file(
                    include_path,
                    resolved_boundary,
                    depth + 1,
                    visited,
                )
                if expanded:
                    output.append(expanded)
        finally:
            visited.remove(resolved_path)
        return "\n".join(output)

    def _warn(self, path: Path, message: str) -> None:
        """只记录路径和原因，不读取或暴露目标文件内容。"""

        self._warnings.append(f"{path}: {message}")
