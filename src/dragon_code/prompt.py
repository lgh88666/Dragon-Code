"""Dragon Code 的内置提示词和启动 Banner。"""

from rich.text import Text

SYSTEM_PROMPT = """你是 Dragon Code，一个运行在终端中的 AI 编程助手。
请准确理解用户的问题，给出清晰、简洁且可执行的回答。
当前章节仅支持文本对话，不要声称自己已经读取文件或执行命令。
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
