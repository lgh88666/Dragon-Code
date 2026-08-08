"""保存当前进程中的对话历史。"""

import copy

from dragon_code.models import ChatMessage


class Conversation:
    """保存当前进程内已经成功完成的对话历史。"""

    def __init__(self):
        self._messages: list[ChatMessage] = []

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

        self._messages.extend(copy.deepcopy(messages))

    def replace_messages(self, messages: list[ChatMessage]) -> None:
        """原子替换全部已提交历史，并与调用方对象解除共享。"""

        replacement = copy.deepcopy(messages)
        self._messages = replacement
