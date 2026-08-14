"""系统提示、环境信息与启动 Banner 测试。"""

import asyncio

from rich.text import Text

import dragon_code.prompt as prompt_module
from dragon_code.prompt import (
    DO_PLAN_PROMPT,
    DRAGON_BANNER,
    PLAN_MODE_PROMPT,
    EnvironmentInfo,
    PromptModule,
    assemble_system_prompt,
    build_system_prompt,
    fixed_prompt_modules,
    gather_environment,
    optional_prompt_modules,
    plan_reminder,
    render_banner,
    runtime_reminder,
    system_reminder,
)


def test_dragon_banner_matches_approved_icon():
    """图标的字符、行数和位置必须与批准版本完全相同。"""

    lines = DRAGON_BANNER.splitlines()

    assert lines == [
        " ▗▄   ▄▖",
        "▐██▙▄▟██▌",
        "▝██▀█▀██▘",
        "  ▘   ▝",
    ]
    assert len(lines) == 4
    assert max(len(line) for line in lines) == 9


def test_old_dragon_features_are_removed():
    assert "<<==<" not in DRAGON_BANNER
    assert ">==>>" not in DRAGON_BANNER
    assert "o o" not in DRAGON_BANNER
    assert "#d13b3b" not in DRAGON_BANNER


def test_render_banner_has_approved_layout():
    rendered = render_banner("0.1.0", r"D:\project")

    assert isinstance(rendered, Text)
    assert rendered.plain.splitlines() == [
        " ▗▄   ▄▖   Dragon Code  v0.1.0",
        "▐██▙▄▟██▌  Multi-provider coding agent",
        r"▝██▀█▀██▘  D:\project",
        "  ▘   ▝",
    ]


def test_render_banner_keeps_special_directory_characters():
    rendered = render_banner("1.2.3", r"D:\My [Demo] Project")

    assert r"D:\My [Demo] Project" in rendered.plain
    assert "v1.2.3" in rendered.plain


def test_render_banner_uses_approved_styles():
    rendered = render_banner("0.1.0", r"D:\project")
    styles = {str(span.style) for span in rendered.spans}

    assert "white" in styles
    assert "bold white" in styles
    assert "grey70" in styles


def test_fixed_modules_are_assembled_in_approved_order():
    modules = fixed_prompt_modules()
    prompt = assemble_system_prompt(list(reversed(modules)))

    assert [module.priority for module in modules] == [10, 20, 30, 40, 50, 60, 70]
    headings = [f"## {module.name}" for module in modules]
    assert [prompt.index(heading) for heading in headings] == sorted(
        prompt.index(heading) for heading in headings
    )
    assert "\n\n\n" not in prompt


def test_optional_modules_skip_empty_content_and_allow_new_module():
    modules = fixed_prompt_modules() + optional_prompt_modules()
    prompt = assemble_system_prompt(modules)

    assert "自定义指令" not in prompt
    assert "Skill" not in prompt
    assert "长期记忆" not in prompt

    modules = fixed_prompt_modules() + optional_prompt_modules(
        custom_instructions="## 自定义指令\n自定义内容"
    )
    modules.extend(
        [
            PromptModule("测试模块", 75, "## 测试模块\n测试内容"),
            PromptModule("空模块", 76, "   "),
        ]
    )
    prompt = assemble_system_prompt(modules)
    assert prompt.index("## 测试模块") < prompt.index("## 自定义指令")
    assert "空模块" not in prompt


def test_environment_render_skips_missing_git_fields():
    environment = EnvironmentInfo(
        working_dir=r"D:\project",
        platform="Windows",
        current_date="2026-08-04",
        version="0.1.0",
        model="test-model",
    ).render()

    assert environment.startswith("<environment>")
    assert r"工作目录：D:\project" in environment
    assert "Git 分支" not in environment
    assert "test-model" in environment
    assert environment.endswith("</environment>")


class FakeGitProcess:
    def __init__(self, stdout: bytes, returncode: int = 0, delay: float = 0):
        self.stdout = stdout
        self.returncode = returncode
        self.delay = delay
        self.killed = False

    async def communicate(self):
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.stdout, b""

    def kill(self):
        self.killed = True

    async def wait(self):
        return self.returncode


async def test_gather_environment_reads_git_summary(monkeypatch, tmp_path):
    process = FakeGitProcess(b"## main...origin/main\n M a.py\n?? b.py\n")

    async def create_process(*_args, **_kwargs):
        return process

    monkeypatch.setattr(prompt_module.asyncio, "create_subprocess_exec", create_process)
    environment = await gather_environment(tmp_path, "0.1.0", "test-model")

    assert environment.git_branch == "main"
    assert environment.git_status == "有 2 个未提交修改"
    assert "a.py" not in environment.render()
    assert "b.py" not in environment.render()


async def test_gather_environment_git_timeout_degrades(monkeypatch, tmp_path):
    process = FakeGitProcess(b"", delay=0.05)

    async def create_process(*_args, **_kwargs):
        return process

    monkeypatch.setattr(prompt_module.asyncio, "create_subprocess_exec", create_process)
    monkeypatch.setattr(prompt_module, "GIT_TIMEOUT_SECONDS", 0.001)
    environment = await gather_environment(tmp_path, "0.1.0", "test-model")

    assert environment.git_branch == ""
    assert environment.git_status == ""
    assert process.killed is True


async def test_gather_environment_git_unavailable_or_nonzero_degrades(monkeypatch, tmp_path):
    async def missing_git(*_args, **_kwargs):
        raise OSError("git unavailable")

    monkeypatch.setattr(prompt_module.asyncio, "create_subprocess_exec", missing_git)
    missing = await gather_environment(tmp_path, "0.1.0", "test-model")
    assert missing.git_branch == ""
    assert missing.git_status == ""

    async def failed_git(*_args, **_kwargs):
        return FakeGitProcess(b"fatal", returncode=128)

    monkeypatch.setattr(prompt_module.asyncio, "create_subprocess_exec", failed_git)
    failed = await gather_environment(tmp_path, "0.1.0", "test-model")
    assert failed.git_branch == ""
    assert failed.git_status == ""


async def test_build_system_prompt_separates_stable_and_environment(monkeypatch, tmp_path):
    async def no_git(*_args, **_kwargs):
        return "", ""

    monkeypatch.setattr(prompt_module, "_gather_git_status", no_git)
    first = await build_system_prompt(tmp_path, "0.1.0", "model-a")
    second = await build_system_prompt(tmp_path / "other", "0.1.0", "model-b")

    assert first.stable == second.stable
    assert "Dragon Code" in first.stable
    assert "修改已有文件前" in first.stable and "Read" in first.stable
    assert str(tmp_path.resolve()) not in first.stable
    assert str(tmp_path.resolve()) in first.environment
    assert "model-b" in second.environment


async def test_skill_summary_is_stable_but_sop_is_dynamic(monkeypatch, tmp_path):
    async def no_git(*_args, **_kwargs):
        return "", ""

    monkeypatch.setattr(prompt_module, "_gather_git_status", no_git)
    system = await build_system_prompt(
        tmp_path,
        "0.1.0",
        "model",
        available_skills="以下 Skill 可用：\n- review: 审查代码",
    )
    reminder = runtime_reminder(1, active_skills="## 已激活 Skill：review\n完整秘密 SOP")

    assert "review: 审查代码" in system.stable
    assert "完整秘密 SOP" not in system.stable
    assert "完整秘密 SOP" in reminder


def test_system_reminder_and_plan_frequency():
    reminder = system_reminder("测试约束")

    assert reminder.startswith("<system-reminder>")
    assert reminder.endswith("</system-reminder>")
    assert "测试约束" in reminder
    assert PLAN_MODE_PROMPT in plan_reminder(1)
    assert PLAN_MODE_PROMPT not in plan_reminder(2)
    assert PLAN_MODE_PROMPT not in plan_reminder(5)
    assert PLAN_MODE_PROMPT in plan_reminder(6)
    assert PLAN_MODE_PROMPT in plan_reminder(11)
    assert "根据上文" in DO_PLAN_PROMPT
    combined = runtime_reminder(1, planning=True, active_skills="Skill SOP")
    assert PLAN_MODE_PROMPT in combined
    assert "Skill SOP" in combined
