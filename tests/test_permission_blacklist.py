import pytest

from dragon_code.permissions import PermissionDecision
from dragon_code.permissions.blacklist import DangerousCommandGuard


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",
        "sudo rm -fr ~",
        "mkfs.ext4 /dev/sda1",
        "dd if=/dev/zero of=/dev/sda",
        "powershell -Command Remove-Item -Recurse -Force C:\\",
        "Clear-Disk -Number 0 -RemoveData",
        "cmd /c rd /s /q C:\\",
        "format C:",
        "wsl -- rm -rf /",
        "echo safe && shutdown /s /t 0",
    ],
)
def test_dangerous_commands_are_denied(command):
    result = DangerousCommandGuard().check(command)
    assert result is not None
    assert result.decision is PermissionDecision.DENY
    assert result.source == "blacklist"


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf build",
        "Remove-Item -Recurse -Force .venv",
        "git status --short",
        "Get-Volume",
        "echo rm -rf /",
        "python -c \"print('shutdown /s')\"",
    ],
)
def test_normal_project_commands_are_not_denied(command):
    assert DangerousCommandGuard().check(command) is None
