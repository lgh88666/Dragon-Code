"""Dragon Code 的内置提示词和启动 Banner。"""

SYSTEM_PROMPT = """你是 Dragon Code，一个运行在终端中的 AI 编程助手。
请准确理解用户的问题，给出清晰、简洁且可执行的回答。
当前章节仅支持文本对话，不要声称自己已经读取文件或执行命令。
"""

# 原创夜行小龙头像：紧凑、终端友好，不复刻具体影视角色。
DRAGON_BANNER = r"""
      /\     /\
  ___/  \___/  \___
 /  \  o     o  /  \
<    \    ^    /    >
 \____\__===__/____/
""".strip("\n")


def render_banner(version: str, cwd: str) -> str:
    """生成包含版本和当前工作目录的启动信息。"""

    return f"{DRAGON_BANNER}\nDragon Code v{version}\n工作目录：{cwd}\n准备就绪，可以开始对话。"
