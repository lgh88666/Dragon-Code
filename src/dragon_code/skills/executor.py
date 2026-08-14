"""编排 inline 与 fork 两种 Skill 执行模式。"""

import asyncio
import copy
from collections.abc import Callable
from dataclasses import replace

from dragon_code.agent import Agent
from dragon_code.clients.base import LLMClient
from dragon_code.context.manager import ContextManager
from dragon_code.models import AgentEvent, ChatMessage, ProviderConfig
from dragon_code.session import Conversation
from dragon_code.skills.manager import SkillManager


def select_fork_history(messages: list[ChatMessage], context: str) -> list[ChatMessage]:
    """按 Skill context 复制合法历史，不共享主会话对象。"""

    if context == "none":
        return []
    if context == "full":
        return copy.deepcopy(messages)

    groups: list[list[ChatMessage]] = []
    current: list[ChatMessage] = []
    for message in messages:
        if message.role == "user" and current:
            groups.append(current)
            current = []
        current.append(message)
    if current:
        groups.append(current)
    recent = [message for group in groups[-5:] for message in group]
    return copy.deepcopy(recent)


class SkillExecutor:
    """执行显式 Skill；所有进度仍通过 AgentEvent 对外发送。"""

    def __init__(
        self,
        manager: SkillManager,
        main_agent: Agent,
        client_factory: Callable[[ProviderConfig], LLMClient],
    ) -> None:
        self.manager = manager
        self.main_agent = main_agent
        self.client_factory = client_factory
        self.child_agent: Agent | None = None

    def request_cancel(self) -> None:
        if self.child_agent is not None:
            self.child_agent.request_cancel()

    async def run_explicit(self, name: str, arguments: str = ""):
        skill, issue = self.manager.refresh_one(name)
        if skill is None:
            yield AgentEvent(type="error", error=ValueError(f"未知 Skill：{name}"))
            return
        if issue is not None:
            yield AgentEvent(type="skill_warning", text=issue.message, skill_name=skill.name)

        yield AgentEvent(
            type="skill_start",
            text=f"正在执行 {skill.mode} Skill：{skill.name}",
            skill_name=skill.name,
        )
        if skill.mode == "inline":
            if self.main_agent.skill_runtime is None:
                yield AgentEvent(
                    type="error",
                    error=ValueError("当前 Agent 没有 SkillRuntime。"),
                    skill_name=skill.name,
                )
                return
            self.main_agent.skill_runtime.activate(skill, arguments)
            task = f"请按照已激活的 {skill.name} Skill 完成任务。"
            async for event in self.main_agent.run(task):
                event.skill_name = skill.name
                yield event
            return

        async for event in self._run_fork(skill, arguments):
            yield event

    async def _run_fork(self, skill, arguments: str):
        history = select_fork_history(
            self.main_agent.conversation.get_messages(),
            skill.context,
        )
        conversation = Conversation(history)
        child_runtime = self.manager.create_runtime()
        child_runtime.activate(skill, arguments)

        config = self.main_agent.client.config
        if skill.model:
            config = replace(config, model=skill.model)
        try:
            client = self.client_factory(config)
        except Exception:
            yield AgentEvent(
                type="error",
                error=ValueError(f"无法为 Skill {skill.name} 创建模型客户端。"),
                skill_name=skill.name,
            )
            return

        context_manager = ContextManager(
            self.main_agent.working_dir,
            summary_client=self.main_agent.context_manager.summary_client,
            context_window=config.context_window,
        )
        child = Agent(
            client,
            conversation,
            self.main_agent.registry,
            self.main_agent.working_dir,
            self.main_agent.version,
            max_iterations=self.main_agent.max_iterations,
            unknown_tool_limit=self.main_agent.unknown_tool_limit,
            permission_engine=self.main_agent.permission_engine,
            approval_controller=self.main_agent.approval_controller,
            permission_mode=self.main_agent.mode,
            context_manager=context_manager,
            custom_instructions=self.main_agent.custom_instructions,
            skill_manager=self.manager,
            skill_runtime=child_runtime,
        )
        self.child_agent = child
        summary = ""
        task = f"请执行 {skill.name} Skill。"
        if arguments.strip():
            task += f"\n用户补充要求：{arguments}"
        try:
            async for event in child.run(task):
                event.skill_name = skill.name
                if event.type == "completed":
                    summary = event.text
                    continue
                yield event
        except asyncio.CancelledError:
            child.request_cancel()
            raise
        finally:
            self.child_agent = None

        if not summary:
            return
        trigger = f"/{skill.name}" + (f" {arguments}" if arguments else "")
        self.main_agent.conversation.commit_messages(
            [
                ChatMessage(role="user", content=trigger),
                ChatMessage(role="assistant", content=summary),
            ]
        )
        yield AgentEvent(
            type="skill_end",
            text=f"Skill {skill.name} 已完成。",
            skill_name=skill.name,
        )
        yield AgentEvent(
            type="completed",
            text=summary,
            usage=child.task_usage,
            skill_name=skill.name,
        )
