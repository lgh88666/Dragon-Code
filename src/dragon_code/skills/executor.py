"""编排 inline 与 fork 两种 Skill 执行模式。"""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Callable
from typing import TYPE_CHECKING

from dragon_code.agent import Agent
from dragon_code.clients.base import LLMClient
from dragon_code.models import AgentEvent, ChatMessage, ProviderConfig, TokenUsage
from dragon_code.skills.manager import SkillManager
from dragon_code.subagents.models import SubAgentKind, SubAgentLaunchRequest

if TYPE_CHECKING:
    from dragon_code.subagents.host import SubAgentHost


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
        subagent_host: SubAgentHost | None = None,
    ) -> None:
        self.manager = manager
        self.main_agent = main_agent
        self.client_factory = client_factory
        self.subagent_host = subagent_host
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
        if self.subagent_host is None:
            yield AgentEvent(
                type="error",
                error=ValueError("当前没有可用的 SubAgentHost。"),
                skill_name=skill.name,
            )
            return
        task = f"请执行 {skill.name} Skill。"
        if arguments.strip():
            task += f"\n用户补充要求：{arguments}"
        try:
            outcome = await self.subagent_host.launch(
                SubAgentLaunchRequest(
                    prompt=task,
                    description=f"执行 {skill.name} Skill",
                    model_override=skill.model or "",
                    kind=SubAgentKind.SKILL_FORK,
                    skill_name=skill.name,
                    skill_arguments=arguments,
                    skill_context=skill.context,
                    skill_allowed_tools=skill.allowed_tools,
                    skill_system_prompt=skill.prompt_body,
                )
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            yield AgentEvent(
                type="error",
                error=ValueError(f"无法启动 Skill {skill.name} 的后台任务。"),
                skill_name=skill.name,
            )
            return
        yield AgentEvent(
            type="skill_end",
            text=f"Skill {skill.name} 已转为后台任务 {outcome.task_id}。",
            skill_name=skill.name,
        )
        yield AgentEvent(
            type="completed",
            text=f"后台任务已启动：{outcome.task_id}",
            usage=TokenUsage(0, 0),
            skill_name=skill.name,
        )
