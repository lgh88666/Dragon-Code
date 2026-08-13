"""不依赖 Textual 的命令补全状态。"""

from dataclasses import dataclass, field

from dragon_code.command.command import Command

MAX_COMPLETION_ROWS = 8


@dataclass
class CompletionState:
    """维护候选、光标和滚动窗口。"""

    items: list[Command] = field(default_factory=list)
    cursor: int = 0
    offset: int = 0
    active: bool = False
    accepted_text: str = ""

    def update(self, items: list[Command]) -> None:
        self.items = list(items)
        self.cursor = 0
        self.offset = 0
        self.active = True

    def hide(self) -> None:
        self.items = []
        self.cursor = 0
        self.offset = 0
        self.active = False

    def move_up(self) -> None:
        if not self.items:
            return
        self.cursor = (self.cursor - 1) % len(self.items)
        self._keep_cursor_visible()

    def move_down(self) -> None:
        if not self.items:
            return
        self.cursor = (self.cursor + 1) % len(self.items)
        self._keep_cursor_visible()

    def selected(self) -> Command | None:
        if not self.items:
            return None
        return self.items[self.cursor]

    def visible_items(self) -> list[Command]:
        return self.items[self.offset : self.offset + MAX_COMPLETION_ROWS]

    def accept(self, text: str) -> None:
        self.accepted_text = text
        self.hide()

    def suppresses(self, text: str) -> bool:
        if self.accepted_text == text:
            # Textual 可能把写回事件和此前的输入事件交错投递。
            # 文本没有再次变化前都不重开菜单，用户继续编辑后再解除抑制。
            return True
        self.accepted_text = ""
        return False

    def _keep_cursor_visible(self) -> None:
        if self.cursor < self.offset:
            self.offset = self.cursor
        elif self.cursor >= self.offset + MAX_COMPLETION_ROWS:
            self.offset = self.cursor - MAX_COMPLETION_ROWS + 1
