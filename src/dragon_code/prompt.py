"""Dragon Code 的内置提示词和启动 Banner。"""

SYSTEM_PROMPT = """你是 Dragon Code，一个运行在终端中的 AI 编程助手。
请准确理解用户的问题，给出清晰、简洁且可执行的回答。
当前章节仅支持文本对话，不要声称自己已经读取文件或执行命令。
"""

# 坦格利安风格三头龙徽章：中央龙头向上，左右龙头向外。
DRAGON_BANNER = r"""
       /^\
  <<==<o o>==>>
 /\/\  \^/  /\/\
<    \ /|\ /    >
 \____V_|_V____/
""".strip("\n")


def render_banner(version: str, cwd: str) -> str:
    """生成包含版本和当前工作目录的启动信息。"""

    return f"{DRAGON_BANNER}\nDragon Code v{version}\n工作目录：{cwd}\n准备就绪，可以开始对话。"
