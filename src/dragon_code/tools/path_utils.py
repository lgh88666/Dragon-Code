"""文件类工具共用的工作目录边界检查。"""

from pathlib import Path

from dragon_code.tools.base import ToolExecutionError


def resolve_workspace_path(workdir: Path, user_path: str) -> Path:
    """解析路径，并确保真实目标仍位于工作目录内。"""

    workspace = workdir.resolve()
    candidate = Path(user_path).expanduser()
    if not candidate.is_absolute():
        candidate = workspace / candidate
    resolved = candidate.resolve(strict=False)

    try:
        resolved.relative_to(workspace)
    except ValueError as error:
        raise ToolExecutionError("path_outside_workspace", "目标路径超出工作目录。") from error
    return resolved


def validate_glob_pattern(pattern: str) -> None:
    """拒绝绝对 glob 和显式的父目录越界。"""

    path = Path(pattern)
    if path.is_absolute() or ".." in path.parts:
        raise ToolExecutionError("path_outside_workspace", "Glob 模式不能超出工作目录。")
