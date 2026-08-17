"""主 Agent 用于委派和管理子任务的五个稳定工具。"""

import json

from pydantic import BaseModel, Field

from dragon_code.models import ToolCall
from dragon_code.subagents.catalog import AgentCatalog
from dragon_code.subagents.host import SubAgentHost
from dragon_code.subagents.manager import BackgroundTaskManager, TaskManagerError
from dragon_code.subagents.models import SubAgentKind, SubAgentLaunchRequest, TaskSnapshot
from dragon_code.tools.base import Tool, ToolExecutionError


class AgentArguments(BaseModel):
    prompt: str = Field(min_length=1, description="交给子 Agent 的完整任务指令。")
    description: str = Field(min_length=1, description="便于任务列表显示的一句话说明。")
    role: str = Field(
        default="",
        description="可选预定义角色名；留空时 Fork 当前对话上下文。",
    )
    model: str = Field(default="", description="定义式子 Agent 可选的完整模型名覆盖。")
    run_in_background: bool = Field(default=False, description="是否立即转为后台任务。")
    name: str = Field(default="", description="可选的唯一任务名称，供 SendMessage 继续任务。")


class TaskListArguments(BaseModel):
    pass


class TaskGetArguments(BaseModel):
    task_id: str = Field(min_length=1, description="要查询的 task ID。")


class TaskStopArguments(BaseModel):
    task_id: str = Field(min_length=1, description="要停止的 running 或 queued task ID。")


class SendMessageArguments(BaseModel):
    name: str = Field(min_length=1, description="已经完成的命名子 Agent 会话。")
    prompt: str = Field(min_length=1, description="继续交给该子 Agent 的新任务。")


def _usage(snapshot: TaskSnapshot) -> dict[str, int | None]:
    return {
        "input_tokens": snapshot.usage.input_tokens,
        "output_tokens": snapshot.usage.output_tokens,
        "cache_write_tokens": snapshot.usage.cache_write_tokens,
        "cache_read_tokens": snapshot.usage.cache_read_tokens,
    }


def _snapshot_data(snapshot: TaskSnapshot, *, include_result: bool) -> dict[str, object]:
    data: dict[str, object] = {
        "id": snapshot.id,
        "name": snapshot.name,
        "description": snapshot.description,
        "kind": snapshot.kind.value,
        "status": snapshot.status.value,
        "created_at": snapshot.created_at.isoformat(),
        "started_at": snapshot.started_at.isoformat() if snapshot.started_at else None,
        "finished_at": snapshot.finished_at.isoformat() if snapshot.finished_at else None,
        "usage": _usage(snapshot),
        "tool_count": snapshot.tool_count,
        "last_activity": snapshot.last_activity.isoformat(),
        "attached": snapshot.attached,
        "queued_position": snapshot.queued_position,
    }
    if include_result:
        data["result"] = snapshot.result
        data["error"] = snapshot.error
    return data


def _json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False)


class AgentTool(Tool):
    name = "Agent"
    category = "system"
    read_only = False
    destructive = False
    is_concurrency_safe = False
    is_system_tool = True
    main_agent_only = True
    arguments_model = AgentArguments
    # 前台任务由 Host 在 120 秒后无损转后台，不能被普通 30 秒工具超时提前取消。
    timeout_seconds = 86_400.0

    def __init__(self, catalog: AgentCatalog, host: SubAgentHost | None = None) -> None:
        self.host = host
        summary = catalog.summary_text() or "- 当前没有可用的预定义角色"
        self.description = (
            "把独立且较复杂的任务委派给子 Agent。role 非空时从干净上下文使用预定义角色；"
            "role 留空时 Fork 当前对话并强制后台。简单的一步操作不要委派。\n可用角色：\n"
            f"{summary}"
        )

    def bind_host(self, host: SubAgentHost) -> None:
        self.host = host

    async def run(self, call: ToolCall, arguments: AgentArguments):
        if self.host is None:
            raise ToolExecutionError("subagent_unavailable", "SubAgentHost 尚未准备完成。")
        kind = SubAgentKind.DEFINED if arguments.role.strip() else SubAgentKind.FORK
        request = SubAgentLaunchRequest(
            prompt=arguments.prompt.strip(),
            description=arguments.description.strip(),
            role_name=arguments.role.strip(),
            model_override=arguments.model.strip(),
            run_in_background=arguments.run_in_background,
            task_name=arguments.name.strip(),
            kind=kind,
        )
        try:
            outcome = await self.host.launch(request, call=call)
        except TaskManagerError as error:
            raise ToolExecutionError("subagent_error", str(error)) from error
        return self._success(
            call,
            _json(
                {
                    "task_id": outcome.task_id,
                    "status": outcome.status,
                    "background": outcome.background,
                    "result": outcome.text,
                }
            ),
        )


class TaskListTool(Tool):
    name = "TaskList"
    description = "列出当前会话的子 Agent 任务摘要、状态以及运行/排队数量。"
    category = "system"
    read_only = True
    destructive = False
    is_concurrency_safe = True
    is_system_tool = True
    main_agent_only = True
    arguments_model = TaskListArguments

    def __init__(self, manager: BackgroundTaskManager) -> None:
        self.manager = manager

    async def run(self, call: ToolCall, arguments: TaskListArguments):
        data = {
            "running": self.manager.running_count(),
            "queued": self.manager.queued_count(),
            "tasks": [
                _snapshot_data(snapshot, include_result=False) for snapshot in self.manager.list()
            ],
        }
        return self._success(call, _json(data))


class TaskGetTool(Tool):
    name = "TaskGet"
    description = "按 task ID 查询子 Agent 的完整状态、结果、用量和工具调用次数。"
    category = "system"
    read_only = True
    destructive = False
    is_concurrency_safe = True
    is_system_tool = True
    main_agent_only = True
    arguments_model = TaskGetArguments

    def __init__(self, manager: BackgroundTaskManager) -> None:
        self.manager = manager

    async def run(self, call: ToolCall, arguments: TaskGetArguments):
        snapshot = self.manager.get(arguments.task_id)
        if snapshot is None:
            raise ToolExecutionError("unknown_task", f"未知任务 ID：{arguments.task_id}")
        return self._success(call, _json(_snapshot_data(snapshot, include_result=True)))


class TaskStopTool(Tool):
    name = "TaskStop"
    description = "停止当前会话中仍在 running 或 queued 的子 Agent 任务。"
    category = "system"
    read_only = False
    destructive = False
    is_concurrency_safe = False
    is_system_tool = True
    main_agent_only = True
    arguments_model = TaskStopArguments

    def __init__(self, manager: BackgroundTaskManager) -> None:
        self.manager = manager

    async def run(self, call: ToolCall, arguments: TaskStopArguments):
        try:
            snapshot = await self.manager.stop(arguments.task_id)
        except TaskManagerError as error:
            raise ToolExecutionError("task_stop_error", str(error)) from error
        return self._success(call, _json(_snapshot_data(snapshot, include_result=True)))


class SendMessageTool(Tool):
    name = "SendMessage"
    description = "向已完成的命名子 Agent 会话追加任务，复用其独立对话并返回新的 task ID。"
    category = "system"
    read_only = False
    destructive = False
    is_concurrency_safe = False
    is_system_tool = True
    main_agent_only = True
    arguments_model = SendMessageArguments

    def __init__(self, host: SubAgentHost | None = None) -> None:
        self.host = host

    def bind_host(self, host: SubAgentHost) -> None:
        self.host = host

    async def run(self, call: ToolCall, arguments: SendMessageArguments):
        if self.host is None:
            raise ToolExecutionError("subagent_unavailable", "SubAgentHost 尚未准备完成。")
        try:
            outcome = await self.host.continue_named(arguments.name, arguments.prompt)
        except TaskManagerError as error:
            raise ToolExecutionError("send_message_error", str(error)) from error
        return self._success(
            call,
            _json(
                {
                    "task_id": outcome.task_id,
                    "status": outcome.status,
                    "background": outcome.background,
                }
            ),
        )


def create_subagent_tools(
    catalog: AgentCatalog,
    manager: BackgroundTaskManager,
) -> tuple[AgentTool, TaskListTool, TaskGetTool, TaskStopTool, SendMessageTool]:
    """按固定顺序创建五个工具；Host 在主 Agent 构造后绑定。"""

    return (
        AgentTool(catalog),
        TaskListTool(manager),
        TaskGetTool(manager),
        TaskStopTool(manager),
        SendMessageTool(),
    )
