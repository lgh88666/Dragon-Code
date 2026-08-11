"""保存当前进程中的对话历史。"""

import copy
from collections.abc import Callable

from dragon_code.models import ChatMessage

AppendCallback = Callable[[ChatMessage], None]
ReplaceCallback = Callable[[list[ChatMessage]], None]


class Conversation:
    """保存当前进程内已经成功完成的对话历史。"""

    def __init__(
        self,
        initial_messages: list[ChatMessage] | None = None,
        on_append: AppendCallback | None = None,
        on_replace: ReplaceCallback | None = None,
    ):
        self._messages = copy.deepcopy(initial_messages or [])
        self._on_append = on_append
        self._on_replace = on_replace
        self._persistence_warning = ""

    def get_messages(self) -> list[ChatMessage]:
        """返回历史副本，避免调用方改坏内部状态。"""

        return copy.deepcopy(self._messages)

    def build_request_messages(self, user_text: str) -> list[ChatMessage]:
        """生成请求消息，但暂时不把用户输入写入历史。"""

        messages = self.get_messages()
        messages.append(ChatMessage(role="user", content=user_text))
        return messages

    def commit_messages(self, messages: list[ChatMessage]) -> None:
        """一次性保存一组已经完成的消息。"""

        committed = copy.deepcopy(messages)
        self._messages.extend(committed)
        if self._on_append is None:
            return
        try:
            for message in committed:
                self._on_append(message)
        except Exception:
            self._persistence_warning = "本轮未能保存"

    def replace_messages(self, messages: list[ChatMessage]) -> None:
        """原子替换全部已提交历史，并与调用方对象解除共享。"""

        replacement = copy.deepcopy(messages)
        self._messages = replacement
        if self._on_replace is None:
            return
        try:
            self._on_replace(copy.deepcopy(replacement))
        except Exception:
            self._persistence_warning = "本轮未能保存"

    def take_persistence_warning(self) -> str:
        """读取并清空最近一次存档失败提示。"""

        warning = self._persistence_warning
        self._persistence_warning = ""
        return warning
