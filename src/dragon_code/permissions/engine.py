"""五层权限判断流水线。"""

from pathlib import Path

from dragon_code.models import ToolCall
from dragon_code.permissions.blacklist import DangerousCommandGuard
from dragon_code.permissions.models import PermissionDecision, PermissionMode, PermissionResult
from dragon_code.permissions.rules import RuleStore
from dragon_code.permissions.sandbox import PathSandbox
from dragon_code.tools.base import Tool


class PermissionEngine:
    """在工具执行前依次应用硬防线、规则和模式。"""

    def __init__(
        self,
        project_root: Path,
        rule_store: RuleStore,
        *,
        blacklist: DangerousCommandGuard | None = None,
        sandbox: PathSandbox | None = None,
    ):
        self.project_root = project_root.resolve()
        self.rule_store = rule_store
        self.blacklist = blacklist or DangerousCommandGuard()
        self.sandbox = sandbox or PathSandbox(self.project_root)

    def check(
        self,
        call: ToolCall,
        tool: Tool | None,
        mode: PermissionMode,
    ) -> PermissionResult:
        if tool is None:
            return PermissionResult(
                PermissionDecision.DENY,
                "unknown_tool",
                f"未注册工具：{call.name}",
            )
        if call.arguments is None:
            return PermissionResult(
                PermissionDecision.DENY,
                "invalid_arguments",
                call.parse_error or "工具参数不是有效 JSON。",
            )

        if call.name == "Bash":
            command = call.arguments.get("command")
            if not isinstance(command, str) or not command.strip():
                return PermissionResult(
                    PermissionDecision.DENY,
                    "invalid_arguments",
                    "Bash 缺少有效的 command。",
                )
            blacklist_result = self.blacklist.check(command)
            if blacklist_result is not None:
                return blacklist_result

        sandbox_result = self.sandbox.check(call)
        if sandbox_result is not None:
            return sandbox_result

        rule_result = self.rule_store.match(call)
        if rule_result is not None:
            return rule_result

        return self._mode_fallback(tool, mode)

    @staticmethod
    def _mode_fallback(tool: Tool, mode: PermissionMode) -> PermissionResult:
        if tool.read_only:
            decision = PermissionDecision.ALLOW
        elif tool.category == "filesystem":
            decision = (
                PermissionDecision.ALLOW
                if mode in {PermissionMode.ACCEPT_EDITS, PermissionMode.BYPASS_PERMISSIONS}
                else PermissionDecision.ASK
            )
        elif tool.category == "command":
            decision = (
                PermissionDecision.ALLOW
                if mode is PermissionMode.BYPASS_PERMISSIONS
                else PermissionDecision.ASK
            )
        else:
            decision = PermissionDecision.DENY

        reason = f"当前 {mode.value} 模式对 {tool.name} 的判断为 {decision.value}。"
        return PermissionResult(decision, "mode", reason)
