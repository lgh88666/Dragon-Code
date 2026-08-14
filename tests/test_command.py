"""Slash Command 核心层测试。"""

from dataclasses import replace
from pathlib import Path

import pytest

from dragon_code.command import (
    Command,
    CommandKind,
    CommandRegistry,
    CommandStatus,
    create_command_registry,
    dispatch_command,
    parse_command,
)


class FakeCommandUI:
    def __init__(self) -> None:
        self.idle = True
        self.calls: list[tuple[str, object]] = []
        self.messages: list[tuple[str, bool]] = []
        self.status = CommandStatus(
            version="0.1.0",
            cwd="/project",
            provider="Fake",
            model="fake-model",
            permission_mode="default",
            session_id="session-1",
            input_tokens=10,
            output_tokens=2,
            cache_write_tokens=3,
            cache_read_tokens=4,
            estimated_context_tokens=20,
            builtin_tool_count=6,
            mcp_tool_count=1,
            user_memory_count=2,
            project_memory_count=3,
        )

    def is_idle(self) -> bool:
        return self.idle

    def show_message(self, text: str, *, error: bool = False) -> None:
        self.messages.append((text, error))

    def open_help(self, commands: list[Command]) -> None:
        self.calls.append(("help", commands))

    def get_status(self) -> CommandStatus:
        return self.status

    def quit(self) -> None:
        self.calls.append(("quit", None))

    def force_compact(self) -> None:
        self.calls.append(("compact", None))

    def clear_session(self) -> None:
        self.calls.append(("clear", None))

    def enter_plan_mode(self) -> None:
        self.calls.append(("plan", None))

    def execute_plan(self) -> None:
        self.calls.append(("do", None))

    def open_sessions(self, *, resume_only: bool = False) -> None:
        self.calls.append(("sessions", resume_only))

    def open_memories(self) -> None:
        self.calls.append(("memory", None))

    def open_permissions(self) -> None:
        self.calls.append(("permission", None))

    def open_review(self) -> None:
        self.calls.append(("review", None))

    def open_skills(self) -> None:
        self.calls.append(("skills", None))

    def hook_items(self):
        return [], []

    def run_skill(self, name: str, arguments: str = "") -> None:
        self.calls.append(("run_skill", (name, arguments)))


async def _empty_handler(_ui) -> None:
    return None


def _command(name: str, aliases: tuple[str, ...] = (), *, hidden: bool = False) -> Command:
    return Command(name, aliases, "描述", f"/{name}", CommandKind.LOCAL, _empty_handler, hidden)


def test_registry_registers_builtin_commands_and_aliases():
    registry = create_command_registry()

    names = [command.name for command in registry.visible()]
    assert names == sorted(
        [
            "exit",
            "plan",
            "do",
            "compact",
            "resume",
            "clear",
            "help",
            "hooks",
            "status",
            "memory",
            "permission",
            "session",
            "skill",
        ]
    )
    assert registry.find("/HELP") is registry.find("h")
    assert registry.find("QUIT") is registry.find("exit")


@pytest.mark.parametrize(
    ("first", "second", "conflict"),
    [
        (_command("help"), _command("HELP"), "help"),
        (_command("help", ("h",)), _command("h"), "h"),
        (_command("help", ("x",)), _command("status", ("X",)), "x"),
    ],
)
def test_registry_rejects_all_name_conflicts(first, second, conflict):
    registry = CommandRegistry()
    registry.register(first)

    with pytest.raises(ValueError, match=conflict):
        registry.register(second)


def test_registry_completion_uses_visible_main_names_only():
    registry = CommandRegistry()
    registry.register(_command("session", ("ss",)))
    registry.register(_command("status", ("state",)))
    registry.register(_command("secret", hidden=True))

    assert [item.name for item in registry.complete("/s")] == ["session", "status"]
    assert registry.complete("/ss") == []
    assert registry.complete("/state") == []


def test_parse_command_distinguishes_plain_and_extra_text():
    assert parse_command("hello") is None
    assert parse_command(" /Help ") == ("help", "")
    assert parse_command("/help extra text") == ("help", "extra text")


async def test_dispatch_plain_unknown_extra_and_busy_inputs():
    registry = create_command_registry()
    ui = FakeCommandUI()

    assert await dispatch_command("普通消息", registry, ui) is False
    assert await dispatch_command("/unknown", registry, ui) is True
    assert "未知命令" in ui.messages[-1][0]

    assert await dispatch_command("/help extra", registry, ui) is True
    assert "不接收参数" in ui.messages[-1][0]

    ui.idle = False
    assert await dispatch_command("/status", registry, ui) is True
    assert "当前任务" in ui.messages[-1][0]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/exit", ("quit", None)),
        ("/Q", ("quit", None)),
        ("/compact", ("compact", None)),
        ("/clear", ("clear", None)),
        ("/plan", ("plan", None)),
        ("/do", ("do", None)),
        ("/resume", ("sessions", True)),
        ("/session", ("sessions", False)),
        ("/memory", ("memory", None)),
        ("/permission", ("permission", None)),
        ("/skill", ("skills", None)),
    ],
)
async def test_builtin_commands_call_expected_ui_capability(text, expected):
    ui = FakeCommandUI()
    await dispatch_command(text, create_command_registry(), ui)
    assert ui.calls[-1] == expected


async def test_help_and_status_are_registry_driven():
    registry = create_command_registry()
    ui = FakeCommandUI()

    await dispatch_command("/help", registry, ui)
    assert ui.calls[-1][0] == "help"
    assert len(ui.calls[-1][1]) == 13

    await dispatch_command("/status", registry, ui)
    text, error = ui.messages[-1]
    assert error is False
    assert "Provider：Fake" in text
    assert "工具：内置 6 / MCP 1" in text


async def test_hooks_command_has_clear_empty_state():
    ui = FakeCommandUI()
    await dispatch_command("/hooks", create_command_registry(), ui)
    assert ui.messages[-1] == ("当前没有加载任何 Hook。", False)


async def test_handler_error_is_recoverable():
    async def broken(_ui) -> None:
        raise RuntimeError("boom")

    registry = CommandRegistry()
    registry.register(replace(_command("broken"), handler=broken))
    ui = FakeCommandUI()

    assert await dispatch_command("/broken", registry, ui) is True
    assert ui.messages[-1] == ("命令执行失败：boom", True)


async def test_dynamic_skill_command_accepts_raw_arguments():
    from dragon_code.skills import SkillDefinition

    skill = SkillDefinition(
        name="demo",
        description="演示",
        prompt_body="SOP $ARGUMENTS",
        allowed_tools=(),
        mode="inline",
        model=None,
        context="full",
        source_level="project",
        source_path=Path("SKILL.md"),
        skill_dir=Path("."),
    )
    registry = create_command_registry([skill])
    ui = FakeCommandUI()

    await dispatch_command("/demo 保留  原始参数", registry, ui)

    assert ui.calls[-1] == ("run_skill", ("demo", "保留  原始参数"))


def test_replace_source_is_atomic_on_conflict():
    registry = CommandRegistry()
    registry.register(_command("help"))
    dynamic = replace(_command("demo"), source="skill")
    registry.replace_source("skill", [dynamic])

    with pytest.raises(ValueError):
        registry.replace_source("skill", [replace(_command("help"), source="skill")])

    assert registry.find("demo") is dynamic
