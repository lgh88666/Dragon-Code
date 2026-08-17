from pathlib import Path

from dragon_code.agent import Agent
from dragon_code.clients.base import LLMClient
from dragon_code.context.manager import ContextManager
from dragon_code.models import (
    ChatMessage,
    LLMEvent,
    ProviderConfig,
    TokenUsage,
    ToolCall,
    ToolResult,
)
from dragon_code.permissions.engine import PermissionEngine
from dragon_code.permissions.rules import RuleStore
from dragon_code.session import Conversation
from dragon_code.skills import SkillExecutor, SkillLoader, SkillManager, select_fork_history
from dragon_code.subagents.catalog import AgentCatalog
from dragon_code.subagents.host import SubAgentHost
from dragon_code.subagents.manager import BackgroundTaskManager
from dragon_code.subagents.models import TaskStatus
from dragon_code.tools.registry import ToolRegistry


class RecordingClient(LLMClient):
    def __init__(self, config, response_text="完成"):
        super().__init__(config)
        self.response_text = response_text
        self.requests = []

    async def stream(self, request):
        self.requests.append(request)
        yield LLMEvent("text_delta", text=self.response_text)
        yield LLMEvent("usage", usage=TokenUsage(3, 2))
        yield LLMEvent("completed", message=ChatMessage("assistant", self.response_text))


def write_skill(root: Path, name: str, *, mode="fork", context="recent", model=None):
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    model_line = f"\nmodel: {model}" if model else ""
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: 测试 {name}\nallowedTools: []\n"
        f"mode: {mode}\ncontext: {context}{model_line}\n---\n执行 SOP：$ARGUMENTS",
        encoding="utf-8",
    )


def make_environment(tmp_path: Path, skill_name="review", **skill_options):
    project = tmp_path / "project"
    write_skill(project / ".dragon-code" / "skills", skill_name, **skill_options)
    manager = SkillManager(
        SkillLoader(project, user_home=tmp_path / "home", builtin_root=tmp_path / "none")
    )
    manager.reload()
    config = ProviderConfig("Fake", "openai", "key", "main-model")
    main_client = RecordingClient(config, "主回复")
    conversation = Conversation()
    main_agent = Agent(
        main_client,
        conversation,
        ToolRegistry(),
        project,
        "test",
        permission_engine=PermissionEngine(project, RuleStore.empty(project)),
        context_manager=ContextManager(project),
        skill_manager=manager,
        skill_runtime=manager.create_runtime(),
    )
    created = []

    def factory(child_config):
        client = RecordingClient(child_config, "子任务摘要")
        created.append(client)
        return client

    task_manager = BackgroundTaskManager()
    host = SubAgentHost(AgentCatalog(()), task_manager, factory)
    host.bind_parent(main_agent)
    return manager, main_agent, factory, created, task_manager, host


async def wait_terminal(task_manager: BackgroundTaskManager, task_id: str):
    for _ in range(200):
        snapshot = task_manager.get(task_id)
        if snapshot is not None and snapshot.status in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }:
            return snapshot
        import asyncio

        await asyncio.sleep(0.001)
    raise AssertionError("Skill 后台任务没有结束")


def test_select_fork_history_full_recent_none_and_copy():
    messages = []
    for index in range(7):
        messages.extend(
            [
                ChatMessage("user", f"u{index}"),
                ChatMessage("assistant", tool_calls=[ToolCall(str(index), "Read", {})]),
                ChatMessage(
                    "tool",
                    tool_results=[ToolResult(str(index), "Read", True, "ok")],
                ),
            ]
        )

    assert len(select_fork_history(messages, "full")) == 21
    recent = select_fork_history(messages, "recent")
    assert len(recent) == 15
    assert recent[0].content == "u2"
    assert select_fork_history(messages, "none") == []
    recent[0].content = "changed"
    assert messages[6].content == "u2"


async def test_fork_events_and_summary_return_as_background_notification(tmp_path: Path):
    manager, main_agent, factory, created, task_manager, host = make_environment(tmp_path)
    executor = SkillExecutor(manager, main_agent, factory, host)

    events = [event async for event in executor.run_explicit("review", "检查 ch11")]

    assert events[0].type == "skill_start"
    assert events[-2].type == "skill_end"
    assert events[-1].type == "completed"
    task_id = events[-1].text.rsplit("：", 1)[-1]
    snapshot = await wait_terminal(task_manager, task_id)
    assert snapshot.result == "主回复"
    assert main_agent.conversation.get_messages() == []
    assert created == []
    await task_manager.close()
    await host.close()


async def test_fork_model_only_overrides_model_name(tmp_path: Path):
    manager, main_agent, factory, created, task_manager, host = make_environment(
        tmp_path,
        skill_name="other",
        model="child-model",
    )
    executor = SkillExecutor(manager, main_agent, factory, host)

    events = [event async for event in executor.run_explicit("other")]
    task_id = events[-1].text.rsplit("：", 1)[-1]
    await wait_terminal(task_manager, task_id)

    child_config = created[0].config
    assert child_config.model == "child-model"
    assert child_config.protocol == main_agent.client.config.protocol
    assert child_config.api_key == main_agent.client.config.api_key
    await task_manager.close()
    await host.close()


async def test_inline_uses_main_agent_and_current_model(tmp_path: Path):
    manager, main_agent, factory, created, _task_manager, _host = make_environment(
        tmp_path,
        skill_name="test",
        mode="inline",
        context="full",
        model="ignored-model",
    )
    executor = SkillExecutor(manager, main_agent, factory)

    events = [event async for event in executor.run_explicit("test", "参数")]

    assert not created
    assert events[-1].type == "completed"
    assert main_agent.client.model == "main-model"
    assert "参数" in main_agent.skill_runtime.reminder_text()
