from dragon_code.agent import Agent
from dragon_code.clients.base import LLMClient
from dragon_code.hooks import HookEngine
from dragon_code.hooks.models import (
    HookAction,
    HookActionType,
    HookDefinition,
    HookEvent,
    HookExecution,
    HookSnapshot,
)
from dragon_code.models import ChatMessage, LLMEvent, ProviderConfig, TokenUsage, ToolCall
from dragon_code.session import Conversation
from dragon_code.tools.registry import ToolRegistry


class SequenceClient(LLMClient):
    def __init__(self, responses):
        super().__init__(ProviderConfig("Fake", "openai", "key", "model"))
        self.responses = list(responses)
        self.requests = []

    async def stream(self, request):
        self.requests.append(request)
        response_value = self.responses.pop(0)
        if isinstance(response_value, Exception):
            raise response_value
        for event in response_value:
            yield event


def response(content="", calls=None):
    calls = calls or []
    return [
        *[LLMEvent("tool_call", tool_call=call) for call in calls],
        LLMEvent("usage", usage=TokenUsage(2, 1)),
        LLMEvent("completed", message=ChatMessage("assistant", content, tool_calls=calls)),
    ]


def definition(name, event, action):
    return HookDefinition(name, event, None, action, timeout=1)


def make_agent(tmp_path, client, engine):
    return Agent(
        client,
        Conversation(),
        ToolRegistry(),
        tmp_path,
        "test",
        hook_engine=engine,
    )


async def collect(agent, text="执行"):
    return [event async for event in agent.run(text)]


async def test_pre_user_prompt_notification_enters_request_but_not_history(tmp_path):
    hook = definition(
        "remind",
        HookEvent.PRE_USER_MESSAGE,
        HookAction(HookActionType.PROMPT, prompt="remember {{iteration}}"),
    )
    engine = HookEngine(HookSnapshot((hook,)))
    client = SequenceClient([response("完成")])
    agent = make_agent(tmp_path, client, engine)

    await collect(agent)

    assert "<hook-notification>" in client.requests[0].reminder
    assert "remember 1" in client.requests[0].reminder
    assert all(
        "hook-notification" not in message.content for message in agent.conversation.get_messages()
    )


class BlockingExecutor:
    async def execute(self, hook, _context):
        return HookExecution(hook.name, hook.action.type, "blocked", "test denied", True)


class RecordingExecutor:
    def __init__(self):
        self.events = []

    async def execute(self, hook, context):
        self.events.append(context.event)
        return HookExecution(hook.name, hook.action.type, "success", "recorded")


async def test_user_prompt_block_keeps_history_empty_and_skips_model(tmp_path):
    hook = definition(
        "block-input",
        HookEvent.USER_PROMPT_SUBMIT,
        HookAction(HookActionType.SHELL, command="unused"),
    )
    engine = HookEngine(HookSnapshot((hook,)))
    engine.executor = BlockingExecutor()
    client = SequenceClient([])
    agent = make_agent(tmp_path, client, engine)

    events = await collect(agent, "blocked text")

    assert [event.type for event in events] == ["hook", "user_rejected"]
    assert events[-1].rejected_text == "blocked text"
    assert agent.conversation.get_messages() == []
    assert client.requests == []


async def test_pre_tool_block_returns_paired_structured_result(tmp_path):
    hook = definition(
        "block-tool",
        HookEvent.PRE_TOOL_USE,
        HookAction(HookActionType.SHELL, command="unused"),
    )
    engine = HookEngine(HookSnapshot((hook,)))
    engine.executor = BlockingExecutor()
    call = ToolCall("call-1", "Unknown", {"path": "blocked.txt"})
    client = SequenceClient([response(calls=[call]), response("已调整")])
    agent = make_agent(tmp_path, client, engine)

    events = await collect(agent)

    tool_results = [event.tool_result for event in events if event.tool_result is not None]
    assert tool_results[0].error_code == "hook_denied"
    history = agent.conversation.get_messages()
    assert history[1].tool_calls[0].id == history[2].tool_results[0].call_id
    assert history[-1].content == "已调整"


async def test_agent_triggers_turn_tool_compact_and_notification_events(tmp_path):
    from dragon_code.clients.base import LLMError

    watched = (
        HookEvent.USER_PROMPT_SUBMIT,
        HookEvent.PRE_USER_MESSAGE,
        HookEvent.PRE_TOOL_USE,
        HookEvent.POST_TOOL_USE,
        HookEvent.PRE_COMPACT,
        HookEvent.POST_COMPACT,
        HookEvent.STOP,
        HookEvent.NOTIFICATION,
    )
    hooks = tuple(
        definition(
            f"watch-{event.value}",
            event,
            HookAction(HookActionType.SUBAGENT, task="record"),
        )
        for event in watched
    )
    engine = HookEngine(HookSnapshot(hooks))
    recorder = RecordingExecutor()
    engine.executor = recorder
    call = ToolCall("call-1", "Unknown", {})
    client = SequenceClient([response(calls=[call]), response("完成")])
    agent = make_agent(tmp_path, client, engine)

    await collect(agent)
    _compact_events = [event async for event in agent.compact_context()]

    failing_client = SequenceClient([LLMError("network", "offline")])
    failing_agent = make_agent(tmp_path, failing_client, engine)
    await collect(failing_agent)

    assert set(watched).issubset(set(recorder.events))
