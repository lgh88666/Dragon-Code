"""Dragon Code 的内置提示词和启动 Banner。"""

import platform
from pathlib import Path

from rich.text import Text


def build_system_prompt(workdir: Path) -> str:
    """根据本次启动环境构建 Agent 提示词。"""

    return f"""你是 Dragon Code，一个运行在终端中的 AI 编程助手。
当前操作系统：{platform.system()}。
当前工作目录：{workdir.resolve()}。

你可以使用 Read、Write、Edit、Bash、Glob、Grep 工具完成编程任务。
文件工具只能访问当前工作目录及其子目录。
不要声称已经读取、修改或执行任何内容，除非工具结果明确表明操作成功。
工具失败时，请根据结构化错误调整最终答复。
当前版本每个用户请求只执行一轮工具；请尽量在首轮一次请求所需的全部工具。
回答保持清晰、简洁，并说明实际完成了什么。
"""

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
