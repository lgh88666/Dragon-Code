"""命令补全状态机测试。"""

from dragon_code.command import Command, CommandKind, CompletionState
from dragon_code.command.completion import MAX_COMPLETION_ROWS


async def _handler(_ui) -> None:
    return None


def command(name: str) -> Command:
    return Command(name, (), "描述", f"/{name}", CommandKind.LOCAL, _handler)


def test_completion_moves_and_wraps():
    state = CompletionState()
    state.update([command("a"), command("b"), command("c")])

    state.move_up()
    assert state.selected().name == "c"
    state.move_down()
    assert state.selected().name == "a"


def test_completion_scrolls_at_eight_rows():
    state = CompletionState()
    state.update([command(str(index)) for index in range(10)])

    for _ in range(9):
        state.move_down()

    assert state.cursor == 9
    assert state.offset == 2
    assert len(state.visible_items()) == MAX_COMPLETION_ROWS


def test_completion_accept_suppresses_programmatic_change_once():
    state = CompletionState()
    state.update([command("help")])

    state.accept("/help")
    assert state.active is False
    assert state.suppresses("/help") is True
    assert state.suppresses("/hel") is False


def test_completion_handles_empty_items():
    state = CompletionState()
    state.update([])
    state.move_down()
    state.move_up()

    assert state.active is True
    assert state.selected() is None
    assert state.visible_items() == []
