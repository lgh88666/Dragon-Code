"""Agent 与 TUI 之间的一次性异步审批协调。"""

import asyncio

from dragon_code.permissions.models import ApprovalChoice


class ApprovalController:
    """保存当前唯一待回答的权限确认。"""

    def __init__(self):
        self.call_id = ""
        self.future: asyncio.Future[ApprovalChoice] | None = None

    def begin(self, call_id: str) -> asyncio.Future[ApprovalChoice]:
        if self.future is not None and not self.future.done():
            raise RuntimeError("已经存在等待回答的权限确认。")
        self.call_id = call_id
        self.future = asyncio.get_running_loop().create_future()
        return self.future

    def resolve(self, call_id: str, choice: ApprovalChoice) -> None:
        if call_id != self.call_id or self.future is None or self.future.done():
            return
        future = self.future
        self._clear()
        future.set_result(choice)

    def cancel(self) -> None:
        if self.future is None or self.future.done():
            self._clear()
            return
        future = self.future
        self._clear()
        future.cancel()

    def _clear(self) -> None:
        self.call_id = ""
        self.future = None
