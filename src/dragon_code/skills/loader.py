"""按项目级、用户级、内置级发现 Skill。"""

from dataclasses import replace
from importlib import resources
from pathlib import Path

from dragon_code.skills.directory import load_tool_specs
from dragon_code.skills.parser import (
    SkillDefinition,
    SkillLoadIssue,
    SkillParseError,
    parse_skill_file,
)


class SkillLoader:
    """读取 Skill 文件，但不保存会话级激活状态。"""

    def __init__(
        self,
        project_root: Path,
        *,
        user_home: Path | None = None,
        builtin_root: Path | None = None,
        reserved_commands: set[str] | None = None,
        base_tool_names: set[str] | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.user_home = (user_home or Path.home()).resolve()
        self.builtin_root = builtin_root
        self.reserved_commands = {name.lower() for name in reserved_commands or set()}
        self.base_tool_names = set(base_tool_names or set())

    def _roots(self) -> list[tuple[str, Path]]:
        builtin = self.builtin_root
        if builtin is None:
            builtin = Path(str(resources.files("dragon_code") / "builtin_skills"))
        return [
            ("project", self.project_root / ".dragon-code" / "skills"),
            ("user", self.user_home / ".dragon-code" / "skills"),
            ("builtin", builtin),
        ]

    @staticmethod
    def _candidates(root: Path) -> list[Path]:
        if not root.is_dir():
            return []
        result = []
        for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
            if child.is_file() and child.suffix.lower() == ".md":
                result.append(child)
            elif child.is_dir() and (child / "SKILL.md").is_file():
                result.append(child / "SKILL.md")
        return result

    def _load_one(self, path: Path, level: str) -> SkillDefinition:
        skill = parse_skill_file(path, level)
        if skill.name in self.reserved_commands:
            raise SkillParseError(f"Skill 名称与内置命令冲突：{skill.name}")
        custom_tools = (
            load_tool_specs(skill.name, skill.skill_dir) if path.name == "SKILL.md" else ()
        )
        available = self.base_tool_names | {tool.name for tool in custom_tools} | {"LoadSkill"}
        missing = [name for name in skill.allowed_tools if name not in available]
        if missing:
            raise SkillParseError(f"allowedTools 引用了不存在的工具：{', '.join(missing)}")
        return replace(skill, custom_tools=custom_tools)

    def load_all(self) -> tuple[tuple[SkillDefinition, ...], tuple[SkillLoadIssue, ...]]:
        """返回稳定有序的定义与问题，同名时保留高优先级。"""

        selected: dict[str, SkillDefinition] = {}
        issues = []
        for level, root in self._roots():
            for path in self._candidates(root):
                try:
                    skill = self._load_one(path, level)
                except SkillParseError as error:
                    issues.append(SkillLoadIssue(path, "invalid_skill", str(error)))
                    continue
                if skill.name not in selected:
                    selected[skill.name] = skill
        skills = tuple(sorted(selected.values(), key=lambda item: item.name))
        return skills, tuple(issues)

    def reload_one(
        self, previous: SkillDefinition
    ) -> tuple[SkillDefinition, SkillLoadIssue | None]:
        """重读单个来源，失败时返回旧版本和 warning。"""

        try:
            return self._load_one(previous.source_path, previous.source_level), None
        except SkillParseError as error:
            return previous, SkillLoadIssue(previous.source_path, "reload_failed", str(error))
