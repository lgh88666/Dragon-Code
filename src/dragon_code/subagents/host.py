"""根据角色或父历史创建隔离的子 Agent。"""

from __future__ import annotations

import asyncio
import copy
import uuid
from collections.abc import Callable
from dataclasses import replace

from dragon_code.agent import Agent
from dragon_code.clients.base import LLMClient
from dragon_code.context.manager import ContextManager
from dragon_code.models import AgentEvent, ChatMessage, ProviderConfig, TokenUsage, ToolCall
from dragon_code.permissions import PermissionMode
from dragon_code.session import Conversation
from dragon_code.subagents.catalog import AgentCatalog
from dragon_code.subagents.filtering import filter_subagent_registry
from dragon_code.subagents.fork import build_fork_messages
from dragon_code.subagents.manager import BackgroundTaskManager, TaskManagerError
from dragon_code.subagents.models import (
    AgentDefinition,
    QuerySource,
    SubAgentKind,
    SubAgentLaunchOutcome,
    SubAgentLaunchRequest,
    SubAgentResult,
    SubAgentSession,
    TaskStatus,
)


def _select_recent_history(messages: list[ChatMessage], context: str) -> list[ChatMessage]:
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
    return copy.deepcopy([message for group in groups[-5:] for message in group])


class SubAgentHost:
    """创建子 Agent，但把排队和状态机交给 BackgroundTaskManager。"""

    def __init__(
        self,
        catalog: AgentCatalog,
        manager: BackgroundTaskManager,
        client_factory: Callable[[ProviderConfig], LLMClient],
    ) -> None:
        self.catalog = catalog
        self.manager = manager
        self.client_factory = client_factory
        self.parent: Agent | None = None
        self._sessions: dict[str, SubAgentSession] = {}

    def bind_parent(self, parent: Agent) -> None:
        self.parent = parent
        self.manager.add_sensitive_value(parent.client.config.api_key)

    async def launch(
        self,
        request: SubAgentLaunchRequest,
        *,
        call: ToolCall | None = None,
    ) -> SubAgentLaunchOutcome:
        parent = self._require_parent()
        definition = self._resolve_definition(request)
        background = self._is_background(request, definition)
        session = self._create_session(parent, request, definition, background, call)
        self._sessions[session.key] = session
        prompt_already_in_history = request.kind is not SubAgentKind.DEFINED

        async def runner(task_id: str) -> SubAgentResult:
            return await self._run_session(
                task_id,
                session,
                request.prompt,
                prompt_already_in_history=prompt_already_in_history,
            )

        task = await self.manager.submit(
            session,
            request.prompt,
            runner,
            description=request.description,
            attached=not background,
        )
        if background:
            return SubAgentLaunchOutcome(task.id, task.status.value, background=True)

        try:
            waited = await self.manager.wait_until_detached_or_done(task.id)
        except asyncio.CancelledError:
            try:
                await self.manager.stop(task.id)
            except TaskManagerError:
                pass
            raise
        if waited.reason in {"manual", "timeout"}:
            return SubAgentLaunchOutcome(
                task.id,
                f"{waited.reason}_background",
                background=True,
            )
        if waited.task.status is TaskStatus.COMPLETED:
            return SubAgentLaunchOutcome(task.id, "completed", text=waited.task.result)
        return SubAgentLaunchOutcome(
            task.id,
            waited.task.status.value,
            text=waited.task.error,
        )

    async def continue_named(self, name: str, prompt: str) -> SubAgentLaunchOutcome:
        session = self.manager.session_for_continuation(name)

        async def runner(task_id: str) -> SubAgentResult:
            return await self._run_session(
                task_id,
                session,
                prompt,
                prompt_already_in_history=False,
            )

        task = await self.manager.submit(
            session,
            prompt,
            runner,
            description=f"继续任务 {name}",
            attached=False,
        )
        return SubAgentLaunchOutcome(task.id, task.status.value, background=True)

    def _resolve_definition(self, request: SubAgentLaunchRequest) -> AgentDefinition | None:
        if request.kind is not SubAgentKind.DEFINED:
            return None
        if not request.role_name:
            raise TaskManagerError("定义式子 Agent 缺少角色名。")
        definition = self.catalog.get(request.role_name)
        if definition is None:
            raise TaskManagerError(f"未知 Agent 角色：{request.role_name}")
        return definition

    @staticmethod
    def _is_background(
        request: SubAgentLaunchRequest,
        definition: AgentDefinition | None,
    ) -> bool:
        if request.kind in {SubAgentKind.FORK, SubAgentKind.SKILL_FORK}:
            return True
        return request.run_in_background or bool(definition and definition.background)

    def _create_session(
        self,
        parent: Agent,
        request: SubAgentLaunchRequest,
        definition: AgentDefinition | None,
        background: bool,
        call: ToolCall | None,
    ) -> SubAgentSession:
        source = self._query_source(request.kind)
        planning = parent.mode is PermissionMode.PLAN
        registry = filter_subagent_registry(
            parent.registry,
            definition,
            source=source,
            background=background,
            force_read_only=planning,
        )
        conversation = self._create_conversation(parent, request, call)
        config = self._client_config(parent, request, definition)
        if request.kind is SubAgentKind.DEFINED or (
            request.kind is SubAgentKind.SKILL_FORK and request.model_override
        ):
            client = self._client(config)
        else:
            client = parent.client
        skill_runtime = parent.skill_manager.create_runtime() if parent.skill_manager else None
        if request.kind is SubAgentKind.SKILL_FORK and skill_runtime is not None:
            skill = parent.skill_manager.get(request.skill_name)
            if skill is None:
                raise TaskManagerError(f"未知 Skill：{request.skill_name}")
            skill_runtime.activate(skill, request.skill_arguments)

        context_manager = ContextManager(
            parent.working_dir,
            summary_client=parent.context_manager.summary_client,
            context_window=config.context_window,
        )
        hook_engine = parent.hook_engine.new_session(context_manager.paths.session_id)
        if request.kind is SubAgentKind.DEFINED:
            permission_mode = definition.permission_mode
        else:
            permission_mode = parent.mode
        if planning:
            permission_mode = PermissionMode.PLAN
        custom_instructions = parent.custom_instructions
        stable_override = ""
        if definition is not None:
            custom_instructions = (
                f"{custom_instructions}\n\n## 子 Agent 角色\n{definition.system_prompt}"
            ).strip()
        else:
            stable_override = (
                parent.current_system_prompt.stable if parent.current_system_prompt else ""
            )

        max_iterations = definition.max_iterations if definition else parent.max_iterations
        child = Agent(
            client,
            conversation,
            registry,
            parent.working_dir,
            parent.version,
            max_iterations=max_iterations,
            unknown_tool_limit=parent.unknown_tool_limit,
            permission_engine=parent.permission_engine.new_session(),
            permission_mode=permission_mode,
            context_manager=context_manager,
            custom_instructions=custom_instructions,
            skill_manager=parent.skill_manager,
            skill_runtime=skill_runtime,
            hook_engine=hook_engine,
            query_source=source,
            interactive_permissions=False,
            stable_system_override=stable_override,
        )
        agent_name = definition.name if definition else request.skill_name or "fork"
        may_write = False
        for tool_name in registry.names():
            tool = registry.get(tool_name)
            if tool is not None and not tool.read_only:
                may_write = True
                break
        return SubAgentSession(
            key=uuid.uuid4().hex,
            name=request.task_name,
            kind=request.kind,
            agent_name=agent_name,
            agent=child,
            conversation=conversation,
            hook_engine=hook_engine,
            definition=definition,
            metadata={
                "background": background,
                "may_write": may_write,
            },
        )

    def _create_conversation(
        self,
        parent: Agent,
        request: SubAgentLaunchRequest,
        call: ToolCall | None,
    ) -> Conversation:
        if request.kind is SubAgentKind.DEFINED:
            return Conversation()
        history = parent.conversation.get_messages()
        if request.kind is SubAgentKind.SKILL_FORK:
            history = _select_recent_history(history, request.skill_context)
        pending = parent.pending_assistant_message
        if call is None and request.kind is SubAgentKind.SKILL_FORK:
            pending = None
        messages = build_fork_messages(history, pending, request.prompt)
        return Conversation(messages)

    @staticmethod
    def _query_source(kind: SubAgentKind) -> QuerySource:
        if kind is SubAgentKind.DEFINED:
            return QuerySource.DEFINED_SUBAGENT
        if kind is SubAgentKind.SKILL_FORK:
            return QuerySource.SKILL_FORK
        return QuerySource.FORK_SUBAGENT

    @staticmethod
    def _client_config(
        parent: Agent,
        request: SubAgentLaunchRequest,
        definition: AgentDefinition | None,
    ) -> ProviderConfig:
        if request.kind is SubAgentKind.FORK:
            return parent.client.config
        if request.kind is SubAgentKind.SKILL_FORK:
            model = request.model_override or parent.client.model
            return replace(parent.client.config, model=model)
        model = request.model_override or definition.model
        return replace(parent.client.config, model=model)

    def _client(self, config: ProviderConfig) -> LLMClient:
        try:
            return self.client_factory(config)
        except Exception as error:
            raise TaskManagerError(f"无法创建子 Agent 模型：{config.model}") from error

    async def _run_session(
        self,
        task_id: str,
        session: SubAgentSession,
        prompt: str,
        *,
        prompt_already_in_history: bool,
    ) -> SubAgentResult:
        agent = session.agent
        final_text = ""
        stop_reason = "failed"
        usage = TokenUsage(0, 0)
        tool_count = 0
        async for event in agent.run(
            prompt,
            user_message_in_history=prompt_already_in_history,
        ):
            self.manager.publish_agent_event(task_id, event)
            if event.type == "tool_start":
                tool_count += 1
            if event.usage is not None:
                usage = event.usage
            if event.type == "completed":
                final_text = event.text
                stop_reason = "completed"
            elif event.type == "cancelled":
                final_text = event.text
                stop_reason = "cancelled"
            elif event.type in {"error", "limit", "user_rejected"}:
                final_text = event.text or self._safe_error(event)
                stop_reason = event.type
        return SubAgentResult(final_text, usage, tool_count, stop_reason)

    @staticmethod
    def _safe_error(event: AgentEvent) -> str:
        error = event.error
        message = getattr(error, "message", "")
        return message or "子 Agent 未正常完成。"

    def _require_parent(self) -> Agent:
        if self.parent is None:
            raise TaskManagerError("SubAgentHost 尚未绑定主 Agent。")
        return self.parent

    async def reset_sessions(self) -> None:
        for session in self._sessions.values():
            request_cancel = getattr(session.agent, "request_cancel", None)
            if request_cancel is not None:
                request_cancel()
            await session.hook_engine.close()
        self._sessions.clear()

    async def close(self) -> None:
        await self.reset_sessions()
