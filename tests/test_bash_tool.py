"""Bash 工具测试。"""

import sys

from dragon_code.models import ToolCall
from dragon_code.tools.bash import BashTool


def python_command(code: str) -> str:
    return f'"{sys.executable}" -c "{code}"'


async def test_bash_returns_output_and_exit_code(tmp_path):
    result = await BashTool(tmp_path).execute(
        ToolCall("1", "Bash", {"command": python_command("print('hello')")})
    )
    assert result.success
    assert "hello" in result.metadata["stdout"]
    assert result.metadata["exit_code"] == 0


async def test_bash_nonzero_is_structured(tmp_path):
    result = await BashTool(tmp_path).execute(
        ToolCall("1", "Bash", {"command": python_command("import sys;sys.exit(3)")})
    )
    assert not result.success
    assert result.error_code == "nonzero_exit"
    assert result.metadata["exit_code"] == 3


async def test_bash_timeout(tmp_path):
    tool = BashTool(tmp_path)
    tool.timeout_seconds = 0.05
    result = await tool.execute(
        ToolCall("1", "Bash", {"command": python_command("import time;time.sleep(1)")})
    )
    assert result.error_code == "timeout"
