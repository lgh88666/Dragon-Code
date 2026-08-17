"""加载项目、用户和内置 Agent 定义。"""

from importlib import resources
from pathlib import Path

from dragon_code.subagents.models import (
    AgentDefinition,
    AgentDefinitionIssue,
    AgentDefinitionSource,
)
from dragon_code.subagents.parser import AgentDefinitionError, parse_agent_definition


class BuiltinAgentDefinitionError(RuntimeError):
    """内置定义损坏，应用不能带着不完整角色继续启动。"""


class AgentCatalog:
    def __init__(
        self,
        definitions: tuple[AgentDefinition, ...],
        issues: tuple[AgentDefinitionIssue, ...] = (),
    ) -> None:
        self._definitions = definitions
        self._by_name = {item.name: item for item in definitions}
        self._issues = issues

    def get(self, name: str) -> AgentDefinition | None:
        return self._by_name.get(name)

    def list_definitions(self) -> list[AgentDefinition]:
        return list(self._definitions)

    def issues(self) -> list[AgentDefinitionIssue]:
        return list(self._issues)

    def summary_text(self) -> str:
        return "\n".join(f"- {item.name}: {item.description}" for item in self._definitions)


class AgentDefinitionLoader:
    """启动期创建稳定的 AgentCatalog 快照。"""

    def __init__(
        self,
        project_root: Path,
        *,
        user_home: Path | None = None,
        builtin_root: Path | None = None,
        plugin_roots: tuple[Path, ...] = (),
    ) -> None:
        self.project_root = project_root.resolve()
        self.user_home = (user_home or Path.home()).resolve()
        self.builtin_root = builtin_root
        self.plugin_roots = tuple(path.resolve() for path in plugin_roots)

    def _roots(self) -> list[tuple[AgentDefinitionSource, Path]]:
        builtin = self.builtin_root
        if builtin is None:
            builtin = Path(str(resources.files("dragon_code.subagents") / "builtin"))
        roots = [(AgentDefinitionSource.PLUGIN, path) for path in self.plugin_roots]
        roots.extend(
            [
                (AgentDefinitionSource.BUILTIN, builtin),
                (AgentDefinitionSource.USER, self.user_home / ".dragon-code" / "agents"),
                (AgentDefinitionSource.PROJECT, self.project_root / ".dragon-code" / "agents"),
            ]
        )
        return roots

    @staticmethod
    def _candidates(root: Path) -> list[Path]:
        if not root.is_dir():
            return []
        return sorted(
            (path for path in root.iterdir() if path.is_file() and path.suffix.lower() == ".md"),
            key=lambda path: path.name.lower(),
        )

    def load(self) -> AgentCatalog:
        selected: dict[str, AgentDefinition] = {}
        issues: list[AgentDefinitionIssue] = []
        for source, root in self._roots():
            for path in self._candidates(root):
                try:
                    definition = parse_agent_definition(path, source)
                except AgentDefinitionError as error:
                    if source is AgentDefinitionSource.BUILTIN:
                        raise BuiltinAgentDefinitionError(str(error)) from error
                    issues.append(AgentDefinitionIssue(path.resolve(), "invalid_agent", str(error)))
                    continue
                selected[definition.name] = definition
        definitions = tuple(sorted(selected.values(), key=lambda item: item.name))
        return AgentCatalog(definitions, tuple(issues))
