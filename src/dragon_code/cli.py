"""Dragon Code 命令行入口。"""

import sys

from dragon_code.config import ConfigError, load_config
from dragon_code.tui import DragonCodeApp

DEFAULT_CONFIG_PATH = ".dragon-code/config.yaml"


def main() -> None:
    """加载配置并启动终端界面。"""

    try:
        config = load_config(DEFAULT_CONFIG_PATH)
    except ConfigError as error:
        # 启动错误只显示可读信息，不向用户暴露 Python 堆栈。
        print(f"配置错误：{error}", file=sys.stderr)
        raise SystemExit(1) from None

    DragonCodeApp(config).run()
