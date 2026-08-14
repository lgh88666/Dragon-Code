import json
import sys
from pathlib import Path

import httpx

from dragon_code.hooks.actions import HookActionExecutor
from dragon_code.hooks.models import (
    HookAction,
    HookActionType,
    HookContext,
    HookDefinition,
    HookEvent,
)
from dragon_code.hooks.template import context_json, render_template


def make_hook(action, *, event=HookEvent.STOP, timeout=2):
    return HookDefinition("demo", event, None, action, timeout=timeout)


def make_context(event=HookEvent.STOP, **data):
    return HookContext(event, "session-1", Path.cwd(), "default", data)


def test_template_renders_nested_fields_and_redacts_secrets():
    context = make_context(
        args={"path": "src/a.py"},
        api_key="sentinel",
        headers={"X-API-Key": "header-secret"},
    )
    assert render_template("file={{args.path}}", context) == "file=src/a.py"
    assert "sentinel" not in context_json(context)
    assert "header-secret" not in context_json(context)
    assert "[REDACTED]" in context_json(context)


async def test_shell_receives_context_through_stdin(tmp_path):
    script = tmp_path / "read_context.py"
    script.write_text(
        "import json,sys\nvalue=json.load(sys.stdin)\nprint(value['event'])\n",
        encoding="utf-8",
    )
    command = f'"{sys.executable}" "{script}"'
    hook = make_hook(HookAction(HookActionType.SHELL, command=command))
    result = await HookActionExecutor().execute(hook, make_context())
    assert result.status == "success"
    assert result.message == "Stop"


async def test_shell_exit_two_blocks_only_blocking_event(tmp_path):
    script = tmp_path / "block.py"
    script.write_text(
        "import sys\nprint('blocked reason', file=sys.stderr)\nsys.exit(2)\n", encoding="utf-8"
    )
    command = f'"{sys.executable}" "{script}"'
    action = HookAction(HookActionType.SHELL, command=command)
    blocking = await HookActionExecutor().execute(
        make_hook(action, event=HookEvent.PRE_TOOL_USE),
        make_context(HookEvent.PRE_TOOL_USE),
    )
    normal = await HookActionExecutor().execute(make_hook(action), make_context())
    assert blocking.blocked is True
    assert "blocked reason" in blocking.message
    assert normal.blocked is False
    assert normal.status == "failed"


async def test_shell_timeout_returns_structured_result(tmp_path):
    script = tmp_path / "slow.py"
    script.write_text("import time\ntime.sleep(10)\n", encoding="utf-8")
    command = f'"{sys.executable}" "{script}"'
    hook = make_hook(HookAction(HookActionType.SHELL, command=command), timeout=0.05)

    result = await HookActionExecutor().execute(hook, make_context())

    assert result.status == "timeout"
    assert "超时" in result.message


async def test_shell_does_not_receive_unapproved_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("DRAGON_TEST_SECRET", "must-not-leak")
    script = tmp_path / "read_env.py"
    script.write_text(
        "import os\nprint(os.environ.get('DRAGON_TEST_SECRET', 'missing'))\n",
        encoding="utf-8",
    )
    command = f'"{sys.executable}" "{script}"'
    hook = make_hook(HookAction(HookActionType.SHELL, command=command))

    result = await HookActionExecutor().execute(hook, make_context())

    assert result.status == "success"
    assert result.message == "missing"


async def test_prompt_queues_one_notification():
    reminders = []
    executor = HookActionExecutor(reminders.append)
    action = HookAction(HookActionType.PROMPT, prompt="changed {{tool.name}}")
    result = await executor.execute(make_hook(action), make_context(tool={"name": "Write"}))
    assert result.status == "success"
    assert reminders and "<hook-notification>" in reminders[0]
    assert "changed Write" in reminders[0]


async def test_subagent_is_safe_placeholder():
    action = HookAction(HookActionType.SUBAGENT, task="review")
    result = await HookActionExecutor().execute(make_hook(action), make_context())
    assert result.status == "not_implemented"


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status
        self.is_success = 200 <= status < 300

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.request_data = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def request(self, method, url, **kwargs):
        self.request_data = (method, url, kwargs)
        return self.response


async def test_http_action_can_return_structured_block(monkeypatch):
    fake = FakeClient(FakeResponse({"block": True, "reason": "policy denied"}))
    monkeypatch.setattr(httpx, "AsyncClient", lambda: fake)
    action = HookAction(
        HookActionType.HTTP,
        url="https://example.test/{{session_id}}",
        headers={"X-Event": "{{event}}"},
        body=json.dumps({"path": "{{args.path}}"}),
    )
    event = HookEvent.PRE_TOOL_USE
    result = await HookActionExecutor().execute(
        make_hook(action, event=event), make_context(event, args={"path": "src/a.py"})
    )
    assert result.blocked is True
    assert result.message == "policy denied"
    assert fake.request_data[0] == "POST"
    assert fake.request_data[1].endswith("session-1")
    assert b"src/a.py" in fake.request_data[2]["content"]


async def test_http_non_success_returns_readable_failure(monkeypatch):
    fake = FakeClient(FakeResponse({}, status=503))
    monkeypatch.setattr(httpx, "AsyncClient", lambda: fake)
    action = HookAction(HookActionType.HTTP, url="https://example.test/hook")

    result = await HookActionExecutor().execute(make_hook(action), make_context())

    assert result.status == "failed"
    assert "503" in result.message


async def test_http_exception_is_isolated(monkeypatch):
    class BrokenClient(FakeClient):
        async def request(self, method, url, **kwargs):
            raise httpx.ConnectError("test connection failure")

    monkeypatch.setattr(httpx, "AsyncClient", lambda: BrokenClient(FakeResponse({})))
    action = HookAction(HookActionType.HTTP, url="https://example.test/hook")

    result = await HookActionExecutor().execute(make_hook(action), make_context())

    assert result.status == "failed"
    assert result.message == "Hook 动作执行失败。"
