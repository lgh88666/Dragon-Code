"""Slash Command 的注册、查找和补全。"""

from dragon_code.command.command import Command


def normalize_name(value: str) -> str:
    """把 `/Help` 统一成 `help`。"""

    return value.strip().removeprefix("/").lower()


class CommandRegistry:
    """集中保存全部内置命令。"""

    def __init__(self) -> None:
        self._by_name: dict[str, Command] = {}
        self._commands: list[Command] = []

    def register(self, command: Command) -> None:
        main_name = normalize_name(command.name)
        aliases = tuple(normalize_name(alias) for alias in command.aliases)
        if not main_name:
            raise ValueError("命令名不能为空")

        all_names = (main_name, *aliases)
        if len(set(all_names)) != len(all_names):
            raise ValueError(f"命令名称或别名重复：{command.name}")
        for name in all_names:
            if not name:
                raise ValueError(f"命令 {main_name} 包含空别名")
            if name in self._by_name:
                raise ValueError(f"命令名称或别名冲突：{name}")

        # 保存归一化后的值，显示时统一补上斜杠。
        command.name = main_name
        command.aliases = aliases
        self._commands.append(command)
        for name in all_names:
            self._by_name[name] = command

    def find(self, name: str) -> Command | None:
        return self._by_name.get(normalize_name(name))

    def visible(self) -> list[Command]:
        return sorted(
            (command for command in self._commands if not command.hidden),
            key=lambda command: command.name,
        )

    def complete(self, prefix: str) -> list[Command]:
        normalized = normalize_name(prefix)
        return [command for command in self.visible() if command.name.startswith(normalized)]

    def replace_source(self, source: str, commands: list[Command]) -> None:
        """校验完整新列表后，原子替换某一来源的动态命令。"""

        kept = [command for command in self._commands if command.source != source]
        candidate = CommandRegistry()
        for command in [*kept, *commands]:
            candidate.register(command)
        self._commands = candidate._commands
        self._by_name = candidate._by_name
