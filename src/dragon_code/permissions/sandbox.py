"""文件与搜索工具共用的项目根路径沙箱。"""

import re
from pathlib import Path

from dragon_code.models import ToolCall
from dragon_code.permissions.models import PermissionDecision, PermissionResult

PATH_TOOLS = {"Read", "Write", "Edit", "Glob", "Grep"}
GLOB_CHARS = "*?["


def _deny(reason: str) -> PermissionResult:
    return PermissionResult(PermissionDecision.DENY, "sandbox", reason)


def _glob_root(pattern: str) -> str | PermissionResult:
    normalized = pattern.replace("\\", "/")
    if normalized.startswith(("/", "//")) or re.match(r"^[a-zA-Z]:/", normalized):
        return _deny("Glob 模式不能使用项目外绝对路径。")
    if ".." in Path(normalized).parts:
        return _deny("Glob 模式不能通过 .. 越过项目根目录。")

    wildcard_indexes = [normalized.find(char) for char in GLOB_CHARS]
    wildcard_indexes = [index for index in wildcard_indexes if index >= 0]
    if not wildcard_indexes:
        return str(Path(normalized).parent) if Path(normalized).parent != Path("") else "."

    prefix = normalized[: min(wildcard_indexes)]
    if not prefix:
        return "."
    if prefix.endswith("/"):
        return prefix.rstrip("/") or "."
    parent = Path(prefix).parent
    return str(parent) if str(parent) else "."


def extract_target(call: ToolCall) -> str | PermissionResult | None:
    """提取一次工具调用需要接受沙箱检查的路径。"""

    if call.name == "Bash":
        return None
    if call.name not in PATH_TOOLS:
        # 非文件工具不适用路径沙箱；是否允许由权限引擎的其他层决定。
        return None
    if call.arguments is None:
        return _deny("工具参数不是有效 JSON，无法检查路径。")

    if call.name in {"Read", "Write", "Edit"}:
        target = call.arguments.get("path")
    elif call.name == "Grep":
        target = call.arguments.get("path", ".")
    else:
        pattern = call.arguments.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            return _deny("Glob 缺少有效的 pattern。")
        return _glob_root(pattern)

    if not isinstance(target, str) or not target.strip():
        return _deny("工具缺少有效的路径参数。")
    return target


def _resolve_new_path(candidate: Path) -> Path:
    """通过最近的已存在祖先解析尚未创建的目标。"""

    missing_parts: list[str] = []
    current = candidate
    # dangling symlink 的 exists() 为 False，但仍必须解析它指向的位置。
    while not current.exists() and not current.is_symlink() and current.parent != current:
        missing_parts.append(current.name)
        current = current.parent

    resolved = current.resolve(strict=False)
    for part in reversed(missing_parts):
        resolved /= part
    return resolved


class PathSandbox:
    """确保文件与搜索路径解析后仍在单一项目根内。"""

    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve(strict=True)

    def check(self, call: ToolCall) -> PermissionResult | None:
        target = extract_target(call)
        if target is None:
            return None
        if isinstance(target, PermissionResult):
            return target

        candidate = Path(target).expanduser()
        if not candidate.is_absolute():
            candidate = self.project_root / candidate
        try:
            resolved = (
                candidate.resolve(strict=True)
                if candidate.exists()
                else _resolve_new_path(candidate)
            )
            resolved.relative_to(self.project_root)
        except (OSError, RuntimeError, ValueError):
            return _deny("目标路径解析后超出项目根目录，工具不会执行。")
        return None
