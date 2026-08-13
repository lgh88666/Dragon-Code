"""Slash Command 使用的 Textual 小组件。"""

from rich.text import Text
from textual.widgets import Static

from dragon_code.command.completion import CompletionState


class CommandCompletion(Static):
    """显示输入框当前的命令候选。"""

    def on_mount(self) -> None:
        self.display = False

    def show_state(self, state: CompletionState) -> None:
        if not state.active:
            self.hide_menu()
            return

        text = Text()
        visible = state.visible_items()
        if not visible:
            text.append("  无匹配", style="dim")
        else:
            for row, command in enumerate(visible):
                absolute_index = state.offset + row
                selected = absolute_index == state.cursor
                marker = "❯" if selected else " "
                style = "bold cyan" if selected else "white"
                text.append(f"{marker} /{command.name:<12}", style=style)
                text.append(command.description, style="dim")
                if row < len(visible) - 1:
                    text.append("\n")
        self.update(text)
        self.display = True

    def hide_menu(self) -> None:
        self.display = False
        self.update("")
