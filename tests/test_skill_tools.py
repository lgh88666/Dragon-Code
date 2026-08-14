import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from dragon_code.models import ToolCall
from dragon_code.skills import (
    SkillLoader,
    SkillManager,
    SkillPathArgument,
    SkillToolSpec,
)
from dragon_code.skills.tools import LoadSkillTool, SkillScriptTool


def make_spec(script: Path, **changes) -> SkillToolSpec:
    spec = SkillToolSpec(
        name="skill__demo__run",
        description="运行演示脚本",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        script_path=script,
        read_only=False,
        destructive=True,
        command_arguments=(),
        path_arguments=(SkillPathArgument("path", "write"),) if changes.pop("path", False) else (),
    )
    return replace(spec, **changes)


def write_script(path: Path, source: str) -> Path:
    path.write_text(source, encoding="utf-8")
    return path


async def test_script_success_uses_stdin_and_stdout_json(tmp_path: Path):
    script = write_script(
        tmp_path / "tool.py",
        "import json, sys\n"
        "data=json.load(sys.stdin)\n"
        "print(json.dumps({'success': True, 'content': data['text']}, "
        "ensure_ascii=False))",
    )
    tool = SkillScriptTool(make_spec(script))

    result = await tool.execute(ToolCall("1", tool.name, {"text": "你好"}))

    assert result.success is True
    assert result.content == "你好"


async def test_script_validates_arguments_and_failures(tmp_path: Path):
    bad_json = write_script(tmp_path / "bad.py", "print('not-json')")
    nonzero = write_script(tmp_path / "exit.py", "raise SystemExit(2)")

    missing = await SkillScriptTool(make_spec(bad_json)).execute(ToolCall("1", "x", {}))
    invalid = await SkillScriptTool(make_spec(bad_json)).execute(ToolCall("2", "x", {"text": "ok"}))
    failed = await SkillScriptTool(make_spec(nonzero)).execute(ToolCall("3", "x", {"text": "ok"}))

    assert missing.error_code == "invalid_arguments"
    assert invalid.error_code == "invalid_output"
    assert failed.error_code == "nonzero_exit"


async def test_script_timeout_and_cancel_cleanup(tmp_path: Path):
    script = write_script(tmp_path / "slow.py", "import time\ntime.sleep(10)")
    timeout_tool = SkillScriptTool(make_spec(script), timeout_seconds=0.05)
    assert (
        await timeout_tool.execute(ToolCall("1", timeout_tool.name, {"text": "x"}))
    ).error_code == "timeout"

    cancel_tool = SkillScriptTool(make_spec(script), timeout_seconds=20)
    task = asyncio.create_task(cancel_tool.execute(ToolCall("2", cancel_tool.name, {"text": "x"})))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_script_rejects_oversized_output(tmp_path: Path):
    script = write_script(
        tmp_path / "large.py",
        "import json\nprint(json.dumps({'success': True, 'content': 'x' * 120000}))",
    )
    tool = SkillScriptTool(make_spec(script))
    result = await tool.execute(ToolCall("1", tool.name, {"text": "x"}))
    assert result.error_code == "output_too_large"


async def test_load_skill_returns_short_result_and_activates(tmp_path: Path):
    project = tmp_path / "project"
    directory = project / ".dragon-code" / "skills" / "demo"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        "---\nname: demo\ndescription: 演示\nallowedTools: []\n---\n这是很长的秘密 SOP",
        encoding="utf-8",
    )
    manager = SkillManager(
        SkillLoader(project, user_home=tmp_path / "home", builtin_root=tmp_path / "none")
    )
    manager.reload()
    runtime = manager.create_runtime()
    tool = LoadSkillTool(manager, runtime)

    result = await tool.execute(ToolCall("1", "LoadSkill", {"name": "demo"}))

    assert result.success is True
    assert "秘密 SOP" not in result.content
    assert runtime.active_skills()[0].name == "demo"
    assert tool.is_system_tool is True
