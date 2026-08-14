"""Agent Loop、停止条件、取消和模式测试。"""

import asyncio
from pathlib import Path

from pydantic import BaseModel

from dragon_code.agent import Agent
from dragon_code.clients.base import LLMClient, LLMError
from dragon_code.context.manager import ContextManager
from dragon_code.models import (
    AgentEvent,
    ChatMessage,
    LLMEvent,
    ProviderConfig,
    TokenUsage,
    ToolCall,
)
from dragon_code.permissions import ApprovalChoice, PermissionMode, PermissionRequest
from dragon_code.permissions.engine import PermissionEngine
from dragon_code.permissions.rules import RuleStore
from dragon_code.session import Conversation
from dragon_code.skills import SkillDefinition, SkillRuntime
from dragon_code.tools.base import Tool
from dragon_code.tools.registry import ToolRegistry, create_default_registry


class EmptyArguments(BaseModel):
    pass


class DemoTool(Tool):
    description = "Agent 测试工具"
    category = "test"
    arguments_model = EmptyArguments

    def __init__(
        self,
        name="Demo",
        *,
        safe=True,
        started=None,
        delay=0,
        fail=False,
        result_content=None,
    ):
        self.name = name
        self.is_concurrency_safe = safe
        self.started = started
        self.delay = delay
        self.fail = fail
        self.result_content = result_content
        self.calls = []

    async def run(self, call, arguments):
        self.calls.append(call.id)
        if self.started is not None:
            self.started.set()
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("测试工具主动失败")
        return self._success(call, self.result_content or f"result-{call.id}")


class SequenceClient(LLMClient):
    def __init__(self, responses):
        super().__init__(ProviderConfig("Fake", "openai", "key", "model"))
        self.responses = list(responses)
        self.requests = []

    async def stream(self, request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        for event in response:
            yield event


class BlockingClient(LLMClient):
    def __init__(self):
        super().__init__(ProviderConfig("Fake", "openai", "key", "model"))
        self.started = asyncio.Event()
        self.closed = False

    async def stream(self, request):
        try:
            self.started.set()
            yield LLMEvent("text_delta", text="部分")
            await asyncio.sleep(10)
        finally:
            self.closed = True


def response(content="", calls=None, usage=(10, 2)):
    calls = calls or []
    events = [LLMEvent("tool_call", tool_call=call) for call in calls]
    events.extend(
        [
            LLMEvent("usage", usage=TokenUsage(*usage)),
            LLMEvent(
                "completed",
                message=ChatMessage("assistant", content=content, tool_calls=calls),
            ),
        ]
    )
    return events


def registry_with(*tools):
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


def make_agent(
    client,
    conversation=None,
    registry=None,
    working_dir=None,
    **kwargs,
):
    """用统一的测试环境参数创建 Agent。"""

    return Agent(
        client,
        conversation if conversation is not None else Conversation(),
        registry if registry is not None else ToolRegistry(),
        Path(working_dir) if working_dir is not None else Path.cwd(),
        "test-version",
        **kwargs,
    )


async def collect(agent, text="执行"):
    return [event async for event in agent.run(text)]


async def collect_with_approval(agent, choice, text="执行"):
    """消费事件，并在出现权限确认时立即选择指定答案。"""

    events = []
    async for event in agent.run(text):
        events.append(event)
        if event.type == "permission_request":
            agent.resolve_permission(event.permission_request.call.id, choice)
    return events


class FakeSkillManager:
    def summary_text(self):
        return "以下 Skill 可用：\n- demo: 演示"


VALID_SUMMARY = """<analysis>草稿</analysis><summary>
1. 主要请求和意图：继续任务
2. 关键技术概念：上下文
3. 文件和代码段：无
4. 错误与修复：无
5. 问题解决过程：无
6. 用户消息原文：原话
7. 待办任务：继续
8. 当前工作和停止位置：测试
9. 可能的下一步：实现
</summary>"""


def permission_engine(working_dir, *, load_settings=False):
    root = Path(working_dir)
    rules = (
        RuleStore.load(root, user_home=root / "fake-home")
        if load_settings
        else RuleStore.empty(root)
    )
    return PermissionEngine(root, rules)


def test_permission_event_model_can_hold_request():
    call = ToolCall("1", "Write", {"path": "a.txt", "content": "x"})
    request = PermissionRequest(call, "需要确认", "Write(a.txt)", "Write(a.txt)")
    event = AgentEvent(type="permission_request", permission_request=request)
    assert event.permission_request is request


async def test_active_skill_filters_tools_keeps_system_and_injects_reminder(tmp_path):
    read = DemoTool("Read")
    write = DemoTool("Write")
    system = DemoTool("LoadSkill")
    system.is_system_tool = True
    registry = registry_with(read, write, system)
    runtime = SkillRuntime()
    path = tmp_path / "SKILL.md"
    runtime.activate(
        SkillDefinition(
            name="demo",
            description="演示",
            prompt_body="完整 Skill SOP",
            allowed_tools=("Read",),
            mode="inline",
            model=None,
            context="full",
            source_level="project",
            source_path=path,
            skill_dir=tmp_path,
        )
    )
    client = SequenceClient([response("完成")])
    agent = make_agent(
        client,
        registry=registry,
        working_dir=tmp_path,
        skill_manager=FakeSkillManager(),
        skill_runtime=runtime,
    )

    await collect(agent)

    assert [item.name for item in client.requests[0].tools] == ["Read", "LoadSkill"]
    assert "完整 Skill SOP" in client.requests[0].reminder
    assert "demo: 演示" in client.requests[0].system.stable
    assert "完整 Skill SOP" not in client.requests[0].system.stable


def test_replace_session_clears_active_skills(tmp_path):
    runtime = SkillRuntime()
    path = tmp_path / "SKILL.md"
    runtime.activate(
        SkillDefinition(
            "demo",
            "演示",
            "SOP",
            (),
            "inline",
            None,
            "full",
            "project",
            path,
            tmp_path,
        )
    )
    agent = make_agent(SequenceClient([]), working_dir=tmp_path, skill_runtime=runtime)

    agent.replace_session(Conversation(), ContextManager(tmp_path))

    assert runtime.active_skills() == []


def test_permission_mode_cycles_in_fixed_order():
    client = SequenceClient([response("完成")])
    agent = make_agent(client)

    assert agent.mode is PermissionMode.DEFAULT
    assert agent.cycle_permission_mode() is PermissionMode.ACCEPT_EDITS
    assert agent.cycle_permission_mode() is PermissionMode.PLAN
    assert agent.cycle_permission_mode() is PermissionMode.BYPASS_PERMISSIONS
    assert agent.cycle_permission_mode() is PermissionMode.DEFAULT


async def test_agent_offloads_full_tool_result_before_tui_and_history(tmp_path):
    content = "龙" * 20_000
    tool = DemoTool(result_content=content)
    call = ToolCall("large/read", tool.name, {})
    client = SequenceClient([response(calls=[call]), response("处理完成")])
    conversation = Conversation()
    context_manager = ContextManager(
        tmp_path,
        session_id="1234567890-deadbeef",
    )
    agent = make_agent(
        client,
        conversation=conversation,
        registry=registry_with(tool),
        working_dir=tmp_path,
        permission_engine=permission_engine(tmp_path),
        permission_mode=PermissionMode.BYPASS_PERMISSIONS,
        context_manager=context_manager,
    )

    events = await collect(agent)

    visible_result = next(event.tool_result for event in events if event.type == "tool_end")
    history_result = conversation.get_messages()[2].tool_results[0]
    assert visible_result.content == history_result.content
    assert visible_result.metadata["context_offloaded"] is True
    saved = Path(visible_result.metadata["result_path"])
    assert saved.read_bytes() == content.encode("utf-8")


async def test_agent_warns_safely_when_large_result_cannot_be_saved(tmp_path, monkeypatch):
    content = "x" * 50_001
    tool = DemoTool(result_content=content)
    call = ToolCall("large", tool.name, {})
    client = SequenceClient([response(calls=[call]), response("继续完成")])
    manager = ContextManager(tmp_path, session_id="1234567890-deadbeef")

    def fail_write(path, value):
        raise OSError("secret-path-and-key-must-not-leak")

    monkeypatch.setattr(manager, "_write_result_sync", fail_write)
    agent = make_agent(
        client,
        registry=registry_with(tool),
        working_dir=tmp_path,
        permission_engine=permission_engine(tmp_path),
        permission_mode=PermissionMode.BYPASS_PERMISSIONS,
        context_manager=manager,
    )

    events = await collect(agent)

    warning = next(event for event in events if event.type == "context_warning")
    result = next(event.tool_result for event in events if event.type == "tool_end")
    assert "落盘失败" in warning.text
    assert "secret-path" not in warning.text
    assert result.content == content


async def test_agent_auto_compacts_before_main_request_and_keeps_current_user(tmp_path):
    main_client = SequenceClient([response("主请求完成")])
    summary_client = SequenceClient([response(VALID_SUMMARY)])
    conversation = Conversation()
    conversation.commit_messages(
        [ChatMessage("user", "旧问题"), ChatMessage("assistant", "旧回答")]
    )
    tool = DemoTool()
    tool.description = "x" * 70_000
    context_manager = ContextManager(
        tmp_path,
        session_id="1234567890-deadbeef",
        summary_client=summary_client,
        context_window=50_000,
    )
    agent = make_agent(
        main_client,
        conversation=conversation,
        registry=registry_with(tool),
        working_dir=tmp_path,
        context_manager=context_manager,
    )

    events = await collect(agent, "本轮用户原文")

    phases = [event.compact.phase for event in events if event.compact is not None]
    assert phases[:2] == ["auto_start", "auto_complete"]
    assert main_client.requests[0].messages[-1].content == "本轮用户原文"
    assert summary_client.requests[0].tools == []
    assert conversation.get_messages()[-2].content == "本轮用户原文"


async def test_manual_compact_does_not_call_main_client_or_change_breaker(tmp_path):
    main_client = SequenceClient([])
    summary_client = SequenceClient([response(VALID_SUMMARY)])
    conversation = Conversation()
    conversation.commit_messages([ChatMessage("user", "已有历史")])
    context_manager = ContextManager(
        tmp_path,
        session_id="1234567890-deadbeef",
        summary_client=summary_client,
    )
    context_manager.circuit_breaker.record_failure()
    agent = make_agent(
        main_client,
        conversation=conversation,
        working_dir=tmp_path,
        context_manager=context_manager,
    )

    events = [event async for event in agent.compact_context()]

    assert events[0].compact.phase == "manual_complete"
    assert main_client.requests == []
    assert summary_client.requests[0].tools == []
    assert context_manager.circuit_breaker.consecutive_failures == 1
    assert conversation.get_messages()[0].content.startswith("<summary>")


async def test_auto_summary_happens_before_main_client_call(tmp_path):
    order = []

    class TrackingClient(SequenceClient):
        def __init__(self, label, responses):
            super().__init__(responses)
            self.label = label

        async def stream(self, request):
            order.append(self.label)
            async for event in super().stream(request):
                yield event

    main_client = TrackingClient("main", [response("完成")])
    summary_client = TrackingClient("summary", [response(VALID_SUMMARY)])
    conversation = Conversation()
    conversation.commit_messages([ChatMessage("user", "旧历史")])
    tool = DemoTool()
    tool.description = "x" * 70_000
    agent = make_agent(
        main_client,
        conversation=conversation,
        registry=registry_with(tool),
        working_dir=tmp_path,
        context_manager=ContextManager(
            tmp_path,
            session_id="1234567890-deadbeef",
            summary_client=summary_client,
            context_window=50_000,
        ),
    )

    await collect(agent, "本轮")

    assert order == ["summary", "main"]


async def test_current_user_is_not_committed_when_main_fails_after_auto_compact(tmp_path):
    main_client = SequenceClient([LLMError("network", "主模型失败")])
    summary_client = SequenceClient([response(VALID_SUMMARY)])
    conversation = Conversation()
    conversation.commit_messages([ChatMessage("user", "旧历史")])
    tool = DemoTool()
    tool.description = "x" * 70_000
    agent = make_agent(
        main_client,
        conversation=conversation,
        registry=registry_with(tool),
        working_dir=tmp_path,
        context_manager=ContextManager(
            tmp_path,
            session_id="1234567890-deadbeef",
            summary_client=summary_client,
            context_window=50_000,
        ),
    )

    events = await collect(agent, "不得提交的本轮用户消息")

    assert events[-1].type == "error"
    assert all(
        message.content != "不得提交的本轮用户消息" for message in conversation.get_messages()
    )


async def test_auto_summary_failure_keeps_history_and_continues_main(tmp_path):
    main_client = SequenceClient([response("主模型仍然完成")])
    summary_client = SequenceClient([response("无有效摘要")])
    conversation = Conversation()
    conversation.commit_messages([ChatMessage("user", "旧历史")])
    tool = DemoTool()
    tool.description = "x" * 70_000
    manager = ContextManager(
        tmp_path,
        session_id="1234567890-deadbeef",
        summary_client=summary_client,
        context_window=50_000,
    )
    agent = make_agent(
        main_client,
        conversation=conversation,
        registry=registry_with(tool),
        working_dir=tmp_path,
        context_manager=manager,
    )

    events = await collect(agent, "本轮")

    phases = [event.compact.phase for event in events if event.compact is not None]
    assert "auto_failed" in phases
    assert events[-1].type == "completed"
    assert conversation.get_messages()[0].content == "旧历史"
    assert manager.circuit_breaker.consecutive_failures == 1


async def test_third_auto_summary_failure_emits_circuit_event(tmp_path):
    main_client = SequenceClient(
        [
            response("完成1", usage=(20_000, 100)),
            response("完成2", usage=(20_000, 100)),
            response("完成3", usage=(20_000, 100)),
        ]
    )
    summary_client = SequenceClient([response("无摘要1"), response("无摘要2"), response("无摘要3")])
    tool = DemoTool()
    tool.description = "x" * 70_000
    manager = ContextManager(
        tmp_path,
        session_id="1234567890-deadbeef",
        summary_client=summary_client,
        context_window=50_000,
    )
    agent = make_agent(
        main_client,
        registry=registry_with(tool),
        working_dir=tmp_path,
        context_manager=manager,
    )

    await collect(agent, "第一轮")
    await collect(agent, "第二轮")
    third = await collect(agent, "第三轮")

    phases = [event.compact.phase for event in third if event.compact is not None]
    assert phases == ["auto_start", "auto_failed", "circuit_tripped"]
    assert manager.circuit_breaker.tripped is True


async def test_active_tool_definitions_are_built_once_per_iteration(tmp_path):
    class CountingRegistry(ToolRegistry):
        def __init__(self):
            super().__init__()
            self.definition_calls = 0

        def definitions(self):
            self.definition_calls += 1
            return super().definitions()

    registry = CountingRegistry()
    client = SequenceClient([response("完成")])
    agent = make_agent(client, registry=registry, working_dir=tmp_path)

    await collect(agent)

    assert registry.definition_calls == 1


async def test_blacklist_denial_returns_result_without_execution(tmp_path):
    from dragon_code.tools.bash import BashTool

    bash = BashTool(tmp_path)
    dangerous = ToolCall("danger", "Bash", {"command": "rm -rf /"})
    client = SequenceClient([response(calls=[dangerous]), response("已改用安全方案")])
    agent = make_agent(
        client,
        registry=registry_with(bash),
        working_dir=tmp_path,
        permission_engine=permission_engine(tmp_path),
        permission_mode=PermissionMode.BYPASS_PERMISSIONS,
    )

    events = await collect(agent)
    denial = next(event.tool_result for event in events if event.type == "tool_end")
    assert denial.error_code == "permission_denied"
    assert denial.metadata["permission_source"] == "blacklist"
    assert events[-1].type == "completed"


async def test_write_asks_and_allow_once_executes(tmp_path):
    from dragon_code.tools.file_tools import WriteTool

    write = WriteTool(tmp_path)
    tool_call = ToolCall("write", "Write", {"path": "created.txt", "content": "ok"})
    client = SequenceClient([response(calls=[tool_call]), response("写入完成")])
    agent = make_agent(
        client,
        registry=registry_with(write),
        working_dir=tmp_path,
        permission_engine=permission_engine(tmp_path),
    )

    events = await collect_with_approval(agent, ApprovalChoice.ALLOW_ONCE)
    assert [event.type for event in events].count("permission_request") == 1
    assert (tmp_path / "created.txt").read_text(encoding="utf-8") == "ok"
    assert events[-1].type == "completed"


async def test_user_denial_is_paired_and_agent_continues(tmp_path):
    from dragon_code.tools.file_tools import WriteTool

    write = WriteTool(tmp_path)
    tool_call = ToolCall("write", "Write", {"path": "denied.txt", "content": "no"})
    client = SequenceClient([response(calls=[tool_call]), response("已停止写入")])
    conversation = Conversation()
    agent = make_agent(
        client,
        conversation=conversation,
        registry=registry_with(write),
        working_dir=tmp_path,
        permission_engine=permission_engine(tmp_path),
    )

    events = await collect_with_approval(agent, ApprovalChoice.DENY_ONCE)
    denial = next(event.tool_result for event in events if event.type == "tool_end")
    assert denial.metadata["permission_source"] == "user"
    assert not (tmp_path / "denied.txt").exists()
    assert [message.role for message in conversation.get_messages()] == [
        "user",
        "assistant",
        "tool",
        "assistant",
    ]


async def test_permanent_allow_saves_rule_and_applies_immediately(tmp_path):
    from dragon_code.tools.file_tools import WriteTool

    write = WriteTool(tmp_path)
    first = ToolCall("write-1", "Write", {"path": "saved.txt", "content": "one"})
    second = ToolCall("write-2", "Write", {"path": "saved.txt", "content": "two"})
    client = SequenceClient([response(calls=[first]), response(calls=[second]), response("完成")])
    rules = RuleStore.load(tmp_path, user_home=tmp_path / "fake-home")
    agent = make_agent(
        client,
        registry=registry_with(write),
        working_dir=tmp_path,
        permission_engine=PermissionEngine(tmp_path, rules),
    )

    events = await collect_with_approval(agent, ApprovalChoice.ALLOW_ALWAYS)
    assert [event.type for event in events].count("permission_request") == 1
    settings = tmp_path / ".dragon-code/settings.local.yaml"
    assert "Write(saved.txt)" in settings.read_text(encoding="utf-8")
    assert (tmp_path / "saved.txt").read_text(encoding="utf-8") == "two"


async def test_mcp_allow_session_only_asks_once(tmp_path):
    mcp_tool = DemoTool(name="mcp__local__echo", safe=True)
    first = ToolCall("mcp-1", mcp_tool.name, {"text": "one"})
    second = ToolCall("mcp-2", mcp_tool.name, {"text": "two"})
    client = SequenceClient([response(calls=[first]), response(calls=[second]), response("完成")])
    agent = make_agent(
        client,
        registry=registry_with(mcp_tool),
        working_dir=tmp_path,
        permission_engine=permission_engine(tmp_path),
    )

    events = await collect_with_approval(agent, ApprovalChoice.ALLOW_SESSION)

    assert [event.type for event in events].count("permission_request") == 1
    assert mcp_tool.calls == ["mcp-1", "mcp-2"]
    assert not (tmp_path / ".dragon-code/settings.local.yaml").exists()


async def test_permanent_save_failure_falls_back_to_allow_once(tmp_path, monkeypatch):
    from dragon_code.tools.file_tools import WriteTool

    write = WriteTool(tmp_path)
    tool_call = ToolCall("write", "Write", {"path": "fallback.txt", "content": "ok"})
    client = SequenceClient([response(calls=[tool_call]), response("完成")])
    rules = RuleStore.empty(tmp_path)

    def fail_to_save(_exact_rule):
        raise OSError("模拟本地设置不可写")

    monkeypatch.setattr(rules, "save_local_allow", fail_to_save)
    agent = make_agent(
        client,
        registry=registry_with(write),
        working_dir=tmp_path,
        permission_engine=PermissionEngine(tmp_path, rules),
    )

    events = await collect_with_approval(agent, ApprovalChoice.ALLOW_ALWAYS)
    assert any(event.type == "permission_warning" for event in events)
    assert (tmp_path / "fallback.txt").read_text(encoding="utf-8") == "ok"
    assert rules.match(tool_call) is None


async def test_cancel_during_permission_keeps_history_paired(tmp_path):
    from dragon_code.tools.file_tools import WriteTool

    write = WriteTool(tmp_path)
    tool_call = ToolCall("write", "Write", {"path": "cancelled.txt", "content": "no"})
    client = SequenceClient([response(calls=[tool_call])])
    conversation = Conversation()
    agent = make_agent(
        client,
        conversation=conversation,
        registry=registry_with(write),
        working_dir=tmp_path,
        permission_engine=permission_engine(tmp_path),
    )

    events = []
    async for event in agent.run("写入"):
        events.append(event)
        if event.type == "permission_request":
            agent.request_cancel()

    assert events[-1].type == "cancelled"
    assert not (tmp_path / "cancelled.txt").exists()
    history = conversation.get_messages()
    assert [message.role for message in history] == ["user", "assistant", "tool"]
    assert history[-1].tool_results[0].error_code == "cancelled"


async def test_read_batch_keeps_order_when_one_path_is_denied(tmp_path):
    from dragon_code.tools.file_tools import ReadTool

    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "c.txt").write_text("c", encoding="utf-8")
    calls = [
        ToolCall("a", "Read", {"path": "a.txt"}),
        ToolCall("b", "Read", {"path": "../outside.txt"}),
        ToolCall("c", "Read", {"path": "c.txt"}),
    ]
    client = SequenceClient([response(calls=calls), response("完成")])
    agent = make_agent(
        client,
        registry=registry_with(ReadTool(tmp_path)),
        working_dir=tmp_path,
        permission_engine=permission_engine(tmp_path),
    )

    events = await collect(agent)
    results = [event.tool_result for event in events if event.type == "tool_end"]
    assert [result.call_id for result in results] == ["a", "b", "c"]
    assert [result.success for result in results] == [True, False, True]


async def test_natural_plain_response_commits_once():
    client = SequenceClient([response("完成")])
    conversation = Conversation()
    agent = make_agent(client, conversation, ToolRegistry())

    events = await collect(agent)

    assert [event.type for event in events] == [
        "progress",
        "usage",
        "completed",
    ]
    assert len(client.requests) == 1
    assert "Dragon Code" in client.requests[0].system.stable
    assert "test-version" in client.requests[0].system.environment
    assert client.requests[0].reminder is None
    assert [item.role for item in conversation.get_messages()] == ["user", "assistant"]
    assert events[-1].usage == TokenUsage(10, 2)


async def test_multi_tool_loop_uses_complete_history():
    tool = DemoTool()
    first = ToolCall("1", "Demo", {})
    second = ToolCall("2", "Demo", {})
    client = SequenceClient(
        [
            response(calls=[first]),
            response(calls=[second]),
            response("最终", usage=(5, 1)),
        ]
    )
    conversation = Conversation()
    agent = make_agent(client, conversation, registry_with(tool))

    events = await collect(agent)

    assert tool.calls == ["1", "2"]
    assert len(client.requests) == 3
    assert all(request.system == client.requests[0].system for request in client.requests)
    assert all(request.reminder is None for request in client.requests)
    assert [item.role for item in conversation.get_messages()] == [
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
        "assistant",
    ]
    assert [event.type for event in events].count("tool_start") == 2
    assert events[-1].type == "completed"
    assert events[-1].usage == TokenUsage(25, 5)


async def test_event_order_follows_real_work_order():
    tool = DemoTool()
    call = ToolCall("1", "Demo", {})
    client = SequenceClient(
        [
            [
                LLMEvent("text_delta", text="先检查"),
                *response(calls=[call]),
            ],
            [
                LLMEvent("text_delta", text="已完成"),
                *response("已完成"),
            ],
        ]
    )
    agent = make_agent(client, registry=registry_with(tool))

    events = await collect(agent)

    assert [event.type for event in events] == [
        "progress",
        "text",
        "usage",
        "tool_start",
        "tool_end",
        "progress",
        "text",
        "usage",
        "completed",
    ]


async def test_tool_failure_is_returned_and_agent_continues():
    broken = DemoTool("Broken", fail=True)
    client = SequenceClient(
        [
            response(calls=[ToolCall("1", "Broken", {})]),
            response("已根据失败结果调整"),
        ]
    )
    agent = make_agent(client, registry=registry_with(broken))

    events = await collect(agent)

    result = next(event.tool_result for event in events if event.type == "tool_end")
    assert result.success is False
    assert result.error_code == "tool_error"
    assert events[-1].type == "completed"
    assert len(client.requests) == 2


async def test_unknown_tool_limit_and_history_pairing():
    client = SequenceClient(
        [
            response(calls=[ToolCall("1", "Missing", {})]),
            response(calls=[ToolCall("2", "Missing", {})]),
            response(calls=[ToolCall("3", "Missing", {})]),
        ]
    )
    conversation = Conversation()
    agent = make_agent(
        client,
        conversation,
        ToolRegistry(),
        unknown_tool_limit=3,
    )

    events = await collect(agent)

    assert len(client.requests) == 3
    assert events[-1].type == "limit"
    tool_messages = [item for item in conversation.get_messages() if item.role == "tool"]
    assert [item.tool_results[0].call_id for item in tool_messages] == ["1", "2", "3"]


async def test_valid_tool_resets_unknown_counter():
    demo = DemoTool()
    client = SequenceClient(
        [
            response(calls=[ToolCall("1", "Missing", {})]),
            response(calls=[ToolCall("2", "Missing", {})]),
            response(calls=[ToolCall("3", "Demo", {})]),
            response(calls=[ToolCall("4", "Missing", {})]),
            response(calls=[ToolCall("5", "Missing", {})]),
            response("完成"),
        ]
    )
    agent = make_agent(client, registry=registry_with(demo))

    events = await collect(agent)

    assert events[-1].type == "completed"
    assert len(client.requests) == 6


async def test_iteration_limit_executes_last_tools_without_extra_request():
    demo = DemoTool()
    client = SequenceClient(
        [
            response(calls=[ToolCall("1", "Demo", {})]),
            response(calls=[ToolCall("2", "Demo", {})]),
        ]
    )
    conversation = Conversation()
    agent = make_agent(
        client,
        conversation,
        registry_with(demo),
        max_iterations=2,
    )

    events = await collect(agent)

    assert demo.calls == ["1", "2"]
    assert len(client.requests) == 2
    assert events[-1].type == "limit"
    assert conversation.get_messages()[-1].tool_results[0].call_id == "2"


async def test_stream_error_does_not_commit_incomplete_turn():
    error = LLMError("network", "网络错误")
    conversation = Conversation()
    agent = make_agent(SequenceClient([error]), conversation, ToolRegistry())

    events = await collect(agent)

    assert events[-1].type == "error"
    assert conversation.get_messages() == []


async def test_client_cancel_discards_partial_response():
    client = BlockingClient()
    conversation = Conversation()
    agent = make_agent(client, conversation, ToolRegistry())
    events = []

    async def consume():
        async for event in agent.run("慢回复"):
            events.append(event)

    task = asyncio.create_task(consume())
    await client.started.wait()
    await asyncio.sleep(0)
    agent.request_cancel()
    await task

    assert events[-1].type == "cancelled"
    assert conversation.get_messages() == []
    assert client.closed is True
    assert agent.active_client_task is None


async def test_tool_cancel_keeps_real_unknown_and_unstarted_results():
    slow_started = asyncio.Event()
    fast = DemoTool("Fast", safe=False)
    slow = DemoTool("Slow", safe=False, started=slow_started, delay=10)
    later = DemoTool("Later", safe=False)
    calls = [
        ToolCall("1", "Fast", {}),
        ToolCall("2", "Slow", {}),
        ToolCall("3", "Later", {}),
    ]
    client = SequenceClient([response(calls=calls)])
    conversation = Conversation()
    agent = make_agent(
        client,
        conversation,
        registry_with(fast, slow, later),
    )
    events = []

    async def consume():
        async for event in agent.run("取消工具"):
            events.append(event)

    task = asyncio.create_task(consume())
    await slow_started.wait()
    agent.request_cancel()
    await task

    tool_message = conversation.get_messages()[-1]
    assert [result.error_code for result in tool_message.tool_results] == [
        "",
        "cancel_outcome_unknown",
        "cancelled",
    ]
    assert events[-1].type == "cancelled"
    assert agent.scheduler.active_tasks == {}
    assert later.calls == []


async def test_plan_mode_uses_only_read_tools_and_marks_plan_ready(tmp_path):
    client = SequenceClient([response("计划")])
    agent = make_agent(
        client,
        registry=create_default_registry(tmp_path),
        working_dir=tmp_path,
    )
    agent.enter_plan_mode()

    events = await collect(agent, "分析项目")

    assert events[-1].type == "completed"
    assert agent.can_execute_plan() is True
    assert [tool.name for tool in client.requests[0].tools] == ["Read", "Glob", "Grep"]
    assert "Plan Mode" in client.requests[0].reminder
    agent.enter_default_mode()
    assert agent.can_execute_plan() is False


async def test_plan_mode_does_not_execute_hallucinated_write(tmp_path):
    target = tmp_path / "should-not-exist.txt"
    write_call = ToolCall(
        "write-1",
        "Write",
        {"path": target.name, "content": "禁止写入"},
    )
    client = SequenceClient(
        [
            response(calls=[write_call]),
            response("只输出计划"),
        ]
    )
    agent = make_agent(
        client,
        registry=create_default_registry(tmp_path),
        working_dir=tmp_path,
    )
    agent.enter_plan_mode()

    events = await collect(agent, "先规划")

    result = next(event.tool_result for event in events if event.type == "tool_end")
    assert result.error_code == "unknown_tool"
    assert target.exists() is False
    assert events[-1].type == "completed"


async def test_plan_reminder_is_full_every_five_rounds_and_not_persisted(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("内容", encoding="utf-8")
    calls = [ToolCall(str(index), "Read", {"path": "a.txt"}) for index in range(1, 6)]
    client = SequenceClient([response(calls=[call]) for call in calls] + [response("最终计划")])
    conversation = Conversation()
    agent = make_agent(
        client,
        conversation,
        create_default_registry(tmp_path),
        working_dir=tmp_path,
    )
    agent.enter_plan_mode()

    events = await collect(agent, "制定计划")

    assert events[-1].type == "completed"
    assert len(client.requests) == 6
    assert "不能修改文件" in client.requests[0].reminder
    assert "不能修改文件" not in client.requests[1].reminder
    assert "不能修改文件" in client.requests[5].reminder
    assert all(request.system == client.requests[0].system for request in client.requests)
    assert all("system-reminder" not in item.content for item in conversation.get_messages())


async def test_agent_accumulates_cache_usage():
    tool = DemoTool()
    call = ToolCall("1", "Demo", {})
    client = SequenceClient(
        [
            response(calls=[call], usage=(10, 2, 30, 0)),
            response("完成", usage=(5, 1, 0, 30)),
        ]
    )
    agent = make_agent(client, registry=registry_with(tool))

    events = await collect(agent)

    assert events[-1].usage == TokenUsage(15, 3, 30, 30)


class RecordingMemoryManager:
    def __init__(self, index="remembered preference"):
        self.index = index
        self.calls = []

    def current_index(self):
        return self.index

    def schedule_update(self, client, turn_messages, completed_turns, user_text):
        self.calls.append((client, turn_messages, completed_turns, user_text))


async def test_agent_injects_custom_instructions_and_current_memory(tmp_path):
    client = SequenceClient([response("完成")])
    memory = RecordingMemoryManager()
    agent = make_agent(
        client,
        working_dir=tmp_path,
        custom_instructions="project instruction",
        memory_manager=memory,
    )

    events = await collect(agent, "执行")

    assert events[-1].type == "completed"
    assert "project instruction" in client.requests[0].system.stable
    assert "remembered preference" in client.requests[0].system.stable


async def test_natural_completion_schedules_memory_with_turn_snapshot(tmp_path):
    client = SequenceClient([response("完成")])
    memory = RecordingMemoryManager()
    agent = make_agent(client, working_dir=tmp_path, memory_manager=memory)

    await collect(agent, "请记住偏好")

    assert agent.completed_turns == 1
    assert len(memory.calls) == 1
    _client, messages, turns, user_text = memory.calls[0]
    assert [message.role for message in messages] == ["user", "assistant"]
    assert turns == 1
    assert user_text == "请记住偏好"


async def test_error_and_limit_do_not_schedule_memory(tmp_path):
    memory = RecordingMemoryManager()
    error_agent = make_agent(
        SequenceClient([LLMError("network", "error")]),
        working_dir=tmp_path,
        memory_manager=memory,
    )
    await collect(error_agent)

    tool = DemoTool()
    limit_agent = make_agent(
        SequenceClient([response(calls=[ToolCall("1", "Demo", {})])]),
        registry=registry_with(tool),
        working_dir=tmp_path,
        memory_manager=memory,
        max_iterations=1,
    )
    await collect(limit_agent)

    assert memory.calls == []


async def test_persistence_warning_is_event_and_reply_still_completes(tmp_path):
    def fail(_message):
        raise OSError("disk full")

    conversation = Conversation(on_append=fail)
    agent = make_agent(
        SequenceClient([response("正常回复")]),
        conversation=conversation,
        working_dir=tmp_path,
    )

    events = await collect(agent)

    assert [event.type for event in events[-2:]] == ["session_warning", "completed"]
    assert events[-2].text == "本轮未能保存"
    assert conversation.get_messages()[-1].content == "正常回复"


def test_replace_session_resets_plan_and_recounts_turns(tmp_path):
    agent = make_agent(
        SequenceClient([]),
        working_dir=tmp_path,
    )
    agent.enter_plan_mode()
    agent.has_plan = True
    conversation = Conversation(
        initial_messages=[
            ChatMessage("user", "one"),
            ChatMessage("assistant", "answer"),
            ChatMessage("user", "two"),
        ]
    )
    context = ContextManager(tmp_path, session_id="20260811-120000-abcd")

    agent.replace_session(conversation, context)

    assert agent.conversation is conversation
    assert agent.context_manager is context
    assert agent.completed_turns == 2
    assert agent.mode is PermissionMode.DEFAULT
    assert agent.has_plan is False


def test_replace_session_can_preserve_permission_mode(tmp_path):
    agent = make_agent(SequenceClient([]), working_dir=tmp_path)
    agent.set_permission_mode(PermissionMode.ACCEPT_EDITS)
    agent.has_plan = True

    agent.replace_session(
        Conversation(),
        ContextManager(tmp_path, session_id="20260811-120000-abcd"),
        preserve_mode=True,
    )

    assert agent.mode is PermissionMode.ACCEPT_EDITS
    assert agent.has_plan is False
    assert agent.completed_turns == 0


async def test_read_only_run_uses_read_tools_without_changing_mode(tmp_path):
    client = SequenceClient([response("审查完成")])
    agent = make_agent(
        client,
        registry=create_default_registry(tmp_path),
        working_dir=tmp_path,
        permission_mode=PermissionMode.ACCEPT_EDITS,
    )

    events = [event async for event in agent.run("审查", read_only=True)]

    assert events[-1].type == "completed"
    assert [tool.name for tool in client.requests[0].tools] == ["Read", "Glob", "Grep"]
    assert client.requests[0].reminder is None
    assert agent.mode is PermissionMode.ACCEPT_EDITS
    assert agent.has_plan is False
