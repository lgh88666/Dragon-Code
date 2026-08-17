"""按照来源、后台状态和角色定义过滤子 Agent 工具。"""

from dragon_code.subagents.models import AgentDefinition, QuerySource
from dragon_code.tools.registry import ToolRegistry

MAIN_AGENT_ONLY_TOOLS = {"Agent", "TaskList", "TaskGet", "TaskStop", "SendMessage"}
BACKGROUND_ALLOWED_CORE = {"Read", "Write", "Edit", "Bash", "Glob", "Grep"}


def _background_allowed(name: str) -> bool:
    return name in BACKGROUND_ALLOWED_CORE or name.startswith("mcp__") or name.startswith("skill__")


def filter_subagent_registry(
    registry: ToolRegistry,
    definition: AgentDefinition | None,
    *,
    source: QuerySource,
    background: bool,
    force_read_only: bool = False,
) -> ToolRegistry:
    """按原注册顺序返回子 Agent 可见工具。"""

    if source in {QuerySource.FORK_SUBAGENT, QuerySource.SKILL_FORK}:
        return registry.filtered(lambda _tool: True)

    allowed = set(definition.allowed_tools) if definition else set()
    denied = set(definition.disallowed_tools) if definition else set()

    def keep(tool) -> bool:
        if tool.name in MAIN_AGENT_ONLY_TOOLS or tool.name == "LoadSkill":
            return False
        if background and not _background_allowed(tool.name):
            return False
        if force_read_only and not tool.read_only:
            return False
        if tool.name in denied:
            return False
        if allowed and tool.name not in allowed:
            return False
        return True

    return registry.filtered(keep)
