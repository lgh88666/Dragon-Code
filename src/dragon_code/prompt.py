"""Dragon Code 的系统提示、运行环境提醒和启动 Banner。"""

import asyncio
import platform
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from rich.text import Text

from dragon_code.models import SystemPrompt

GIT_TIMEOUT_SECONDS = 2.0

PLAN_MODE_PROMPT = """
当前处于 Plan Mode。
你只能探索项目、分析需求并形成实现计划，不能修改文件，也不能执行系统命令。
只允许使用 Read、Glob、Grep 获取必要信息。
最终给出清晰、可执行的计划，然后等待用户调整计划或输入 /do。
不要声称已经完成尚未执行的修改。
""".strip()

PLAN_MODE_SHORT_PROMPT = """
当前仍处于 Plan Mode。只使用 Read、Glob、Grep，继续完善计划，不要修改文件或执行命令。
""".strip()

DO_PLAN_PROMPT = """
请根据上文已经确认的最新计划开始执行。使用可用工具完成任务，遇到工具错误时根据结果调整方案，直到给出最终答复。
""".strip()


@dataclass(frozen=True)
class PromptModule:
    """一段职责单一、可按优先级装配的稳定系统指令。"""

    name: str
    priority: int
    content: str


@dataclass(frozen=True)
class EnvironmentInfo:
    """只在当前 Agent 任务中使用的动态环境信息。"""

    working_dir: str
    platform: str
    current_date: str
    git_branch: str = ""
    git_status: str = ""
    version: str = ""
    model: str = ""

    def render(self) -> str:
        """渲染为独立环境块；空字段不会产生空行。"""

        items = [
            ("工作目录", self.working_dir),
            ("操作系统", self.platform),
            ("当前日期", self.current_date),
            ("Git 分支", self.git_branch),
            ("Git 状态", self.git_status),
            ("Dragon Code 版本", self.version),
            ("当前模型", self.model),
        ]
        lines = ["<environment>"]
        lines.extend(f"{name}：{value}" for name, value in items if value)
        lines.append("</environment>")
        return "\n".join(lines)


def fixed_prompt_modules() -> list[PromptModule]:
    """返回七个固定模块；内容不得混入运行时环境。"""

    return [
        PromptModule(
            "身份",
            10,
            "## 身份\n你是 Dragon Code，一个运行在终端中的 AI 编程助手。",
        ),
        PromptModule(
            "系统约束",
            20,
            "## 系统约束\n"
            "保护 API Key 和敏感信息。遵守当前工具边界。"
            "除非工具结果明确成功，否则不得声称已经读取、修改或执行了操作。",
        ),
        PromptModule(
            "任务模式",
            30,
            "## 任务模式\n"
            "默认持续分析、调用工具并根据结果调整，直到任务完成。"
            "收到 <system-reminder> 时，将其视为本轮系统补充约束，不要直接复述。",
        ),
        PromptModule(
            "动作执行",
            40,
            "## 动作执行\n"
            "先了解相关上下文，再执行最小且明确的改动。"
            "工具失败时阅读结构化错误并调整方案；完成后进行必要验证。",
        ),
        PromptModule(
            "工具使用",
            50,
            "## 工具使用\n"
            "优先使用 Read、Write、Edit、Glob、Grep 等专用工具，"
            "不要用 Bash 拼凑专用工具已经能完成的操作。"
            "修改已有文件前必须先使用 Read 读取相关内容；精确修改优先使用 Edit。"
            "只有需要真实执行系统命令时才使用 Bash。",
        ),
        PromptModule(
            "语气风格",
            60,
            "## 语气风格\n回答清晰、直接、友好，使用与用户一致的语言，避免无意义的长篇解释。",
        ),
        PromptModule(
            "文本输出",
            70,
            "## 文本输出\n"
            "使用易读的 Markdown。优先说明实际结果和验证证据；"
            "不要展示隐藏思考过程，也不要伪造未观察到的结果。",
        ),
    ]


def optional_prompt_modules(
    custom_instructions: str = "",
    active_skills: str = "",
    memory: str = "",
) -> list[PromptModule]:
    """返回可选模块；项目指令和长期记忆由 ch09 提供真实来源。"""

    return [
        PromptModule("自定义指令", 80, custom_instructions),
        PromptModule("已激活 Skill", 90, active_skills),
        PromptModule("长期记忆", 100, memory),
    ]


def assemble_system_prompt(modules: list[PromptModule]) -> str:
    """过滤空模块并按优先级稳定装配。"""

    ordered = sorted(modules, key=lambda module: module.priority)
    contents = [module.content.strip() for module in ordered if module.content.strip()]
    return "\n\n".join(contents)


async def gather_environment(
    working_dir: Path,
    version: str,
    model: str,
) -> EnvironmentInfo:
    """快速采集环境；Git 不可用时只省略 Git 信息。"""

    resolved = working_dir.resolve()
    git_branch, git_status = await _gather_git_status(resolved)
    return EnvironmentInfo(
        working_dir=str(resolved),
        platform=platform.platform(),
        current_date=date.today().isoformat(),
        git_branch=git_branch,
        git_status=git_status,
        version=version,
        model=model,
    )


async def _gather_git_status(working_dir: Path) -> tuple[str, str]:
    """读取简短 Git 状态，不读取文件内容或 diff。"""

    try:
        process = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(working_dir),
            "status",
            "--short",
            "--branch",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError:
        return "", ""

    try:
        stdout, _stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        return "", ""

    if process.returncode != 0:
        return "", ""

    lines = stdout.decode("utf-8", errors="replace").splitlines()
    branch = ""
    changed_lines = lines
    if lines and lines[0].startswith("## "):
        branch_text = lines[0][3:]
        branch = branch_text.split("...", 1)[0]
        changed_lines = lines[1:]

    changed_count = len([line for line in changed_lines if line.strip()])
    status = "干净" if changed_count == 0 else f"有 {changed_count} 个未提交修改"
    return branch, status


async def build_system_prompt(
    working_dir: Path,
    version: str,
    model: str,
    *,
    custom_instructions: str = "",
    active_skills: str = "",
    memory: str = "",
) -> SystemPrompt:
    """构造稳定提示和独立环境块。"""

    modules = fixed_prompt_modules()
    modules.extend(optional_prompt_modules(custom_instructions, active_skills, memory))
    stable = assemble_system_prompt(modules)
    environment = await gather_environment(working_dir, version, model)
    return SystemPrompt(stable=stable, environment=environment.render())


def system_reminder(content: str) -> str:
    """把运行时补充指令包装成模型可识别的特殊标签。"""

    return (
        "<system-reminder>\n"
        "以下内容是系统补充约束，请遵守但不要直接复述或单独回答。\n"
        f"{content.strip()}\n"
        "</system-reminder>"
    )


def plan_reminder(iteration: int) -> str:
    """按 1、6、11……轮完整重复 Plan Mode 约束。"""

    prompt = PLAN_MODE_PROMPT if (iteration - 1) % 5 == 0 else PLAN_MODE_SHORT_PROMPT
    return system_reminder(prompt)


# 用户确认的原创翼形图标，字符和位置不要随意调整。
DRAGON_BANNER = """
 ▗▄   ▄▖
▐██▙▄▟██▌
▝██▀█▀██▘
  ▘   ▝
""".strip("\n")


def render_banner(version: str, cwd: str) -> Text:
    """生成图标与产品信息并排的双色启动 Banner。"""

    details = [
        [("Dragon Code", "bold white"), (f"  v{version}", "grey70")],
        [("Multi-provider coding agent", "grey70")],
        [(cwd, "grey70")],
        [],
    ]
    banner = Text()
    icon_lines = DRAGON_BANNER.splitlines()

    for index, icon_line in enumerate(icon_lines):
        # 有右侧信息时补齐图标宽度，让三行文字从同一列开始。
        if details[index]:
            banner.append(icon_line.ljust(9), style="white")
            banner.append("  ")
        else:
            banner.append(icon_line, style="white")

        for content, style in details[index]:
            banner.append(content, style=style)

        if index < len(icon_lines) - 1:
            banner.append("\n")

    return banner
