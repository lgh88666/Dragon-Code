"""Slash Command 的基础数据结构。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dragon_code.command.ui import CommandUI


class CommandKind(Enum):
    """命令的三种执行方式。"""

    LOCAL = "local"
    LOCAL_UI = "local-ui"
    PROMPT = "prompt"


CommandHandler = Callable[["CommandUI"], Awaitable[None]]
CommandArgumentHandler = Callable[["CommandUI", str], Awaitable[None]]


@dataclass
class Command:
    """一条命令的完整元数据。"""

    name: str
    aliases: tuple[str, ...]
    description: str
    usage: str
    kind: CommandKind
    handler: CommandHandler
    hidden: bool = False
    argument_handler: CommandArgumentHandler | None = None
    source: str = "builtin"
