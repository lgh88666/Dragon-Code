"""Dragon Code Slash Command 公共接口。"""

from dragon_code.command.builtins import create_command_registry, create_skill_commands
from dragon_code.command.command import Command, CommandArgumentHandler, CommandHandler, CommandKind
from dragon_code.command.completion import CompletionState
from dragon_code.command.dispatch import dispatch_command, parse_command
from dragon_code.command.registry import CommandRegistry
from dragon_code.command.ui import CommandStatus, CommandUI

__all__ = [
    "Command",
    "CommandArgumentHandler",
    "CommandHandler",
    "CommandKind",
    "CommandRegistry",
    "CommandStatus",
    "CommandUI",
    "CompletionState",
    "dispatch_command",
    "parse_command",
    "create_command_registry",
    "create_skill_commands",
]
