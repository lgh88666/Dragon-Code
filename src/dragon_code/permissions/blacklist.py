"""不可配置的跨平台危险命令黑名单。"""

import re
from dataclasses import dataclass

from dragon_code.permissions.models import PermissionDecision, PermissionResult


@dataclass(frozen=True)
class DangerousPattern:
    """一条固定危险命令规则和给用户看的原因。"""

    regex: re.Pattern[str]
    reason: str


def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


DANGEROUS_PATTERNS = [
    DangerousPattern(
        _compile(
            r"^rm\s+(?=[^\n]*-(?:[a-z]*r[a-z]*f|[a-z]*f[a-z]*r)\b)[^\n]*\s+(?:/|/\*|~)(?:\s|$)"
        ),
        "禁止递归强制删除系统根目录或用户主目录。",
    ),
    DangerousPattern(
        _compile(r"^(?:mkfs(?:\.[a-z0-9]+)?|wipefs)\b"),
        "禁止格式化或清除磁盘文件系统。",
    ),
    DangerousPattern(
        _compile(r"^dd\b[^\n]*\bof=/dev/(?:sd|hd|nvme|vd)[a-z0-9]*\b"),
        "禁止直接覆盖物理磁盘设备。",
    ),
    DangerousPattern(
        _compile(r"^(?:shutdown|reboot|poweroff|halt)\b"),
        "禁止关闭或重启当前系统。",
    ),
    DangerousPattern(
        _compile(
            r"^remove-item\b(?=[^\n]*-(?:recurse|r)\b)(?=[^\n]*-(?:force|fo)\b)[^\n]*(?:[a-z]:[\\/](?:\*|$)|\$env:systemroot)"
        ),
        "禁止递归强制删除 Windows 根目录。",
    ),
    DangerousPattern(
        _compile(r"^(?:clear-disk|format-volume|initialize-disk)\b"),
        "禁止清除或格式化 Windows 磁盘。",
    ),
    DangerousPattern(
        _compile(r"^(?:stop-computer|restart-computer)\b"),
        "禁止关闭或重启当前系统。",
    ),
    DangerousPattern(
        _compile(r"^(?:del|erase|rd|rmdir)\b(?=[^\n]*/s\b)(?=[^\n]*/q\b)[^\n]*[a-z]:[\\/]"),
        "禁止递归静默删除 Windows 根路径。",
    ),
    DangerousPattern(
        _compile(r"^format\s+[a-z]:"),
        "禁止格式化 Windows 磁盘。",
    ),
    DangerousPattern(
        _compile(r"^shutdown\b[^\n]*(?:/s|/r)\b"),
        "禁止关闭或重启当前系统。",
    ),
]

COMMAND_SEPARATORS = re.compile(r"\s*(?:&&|\|\||[;|])\s*")


def _normalize(command: str) -> str:
    return re.sub(r"\s+", " ", command).strip()


def _strip_wrapper(segment: str) -> str:
    """移除 sudo、WSL、PowerShell、CMD 等常见启动前缀。"""

    value = segment.strip().strip("\"'")
    value = re.sub(r"^sudo\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(
        r"^wsl(?:\.exe)?(?:\s+(?:-[^\s]+|--distribution\s+[^\s]+))*\s+(?:--\s*)?",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"^(?:powershell|pwsh)(?:\.exe)?\s+(?:-(?:command|c)\s+)",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"^cmd(?:\.exe)?\s+/(?:c|k)\s+",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return value.strip().strip("\"'")


class DangerousCommandGuard:
    """在 Bash 真正执行前识别固定的高危命令。"""

    def check(self, command: str) -> PermissionResult | None:
        normalized = _normalize(command)
        for segment in COMMAND_SEPARATORS.split(normalized):
            candidate = _strip_wrapper(segment)
            for pattern in DANGEROUS_PATTERNS:
                if pattern.regex.search(candidate):
                    return PermissionResult(
                        decision=PermissionDecision.DENY,
                        source="blacklist",
                        reason=pattern.reason,
                    )
        return None
