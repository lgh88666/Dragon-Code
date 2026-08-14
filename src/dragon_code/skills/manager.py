"""Skill 定义快照与会话级激活状态。"""

from dataclasses import dataclass

from dragon_code.skills.loader import SkillLoader
from dragon_code.skills.parser import (
    ActiveSkill,
    SkillDefinition,
    SkillLoadIssue,
    render_skill_prompt,
)


@dataclass(frozen=True)
class SkillSnapshot:
    """一次完整扫描得到的稳定结果。"""

    skills: tuple[SkillDefinition, ...] = ()
    issues: tuple[SkillLoadIssue, ...] = ()


class SkillRuntime:
    """保存一个 Agent 当前激活的 inline Skills。"""

    def __init__(self) -> None:
        self._active: dict[str, ActiveSkill] = {}

    def activate(self, skill: SkillDefinition, arguments: str = "") -> ActiveSkill:
        active = ActiveSkill(
            name=skill.name,
            rendered_prompt=render_skill_prompt(skill, arguments),
            allowed_tools=skill.allowed_tools,
        )
        self._active[skill.name] = active
        return active

    def clear(self) -> None:
        self._active.clear()

    def active_skills(self) -> list[ActiveSkill]:
        return list(self._active.values())

    def reminder_text(self) -> str:
        sections = []
        for skill in self._active.values():
            sections.append(f"## 已激活 Skill：{skill.name}\n\n{skill.rendered_prompt}")
        return "\n\n".join(sections)

    def allowed_tool_names(self) -> set[str] | None:
        if not self._active:
            return None
        result = set()
        for skill in self._active.values():
            result.update(skill.allowed_tools)
        return result


class SkillManager:
    """保存应用级 Skill 定义，并为 Agent 创建独立 Runtime。"""

    def __init__(self, loader: SkillLoader) -> None:
        self.loader = loader
        self._snapshot = SkillSnapshot()

    def reload(self) -> SkillSnapshot:
        skills, issues = self.loader.load_all()
        snapshot = SkillSnapshot(skills=skills, issues=issues)
        # 新快照完整构造后再替换，调用方不会看到半更新状态。
        self._snapshot = snapshot
        return snapshot

    def get(self, name: str) -> SkillDefinition | None:
        normalized = name.strip().lower()
        for skill in self._snapshot.skills:
            if skill.name == normalized:
                return skill
        return None

    def list_skills(self) -> list[SkillDefinition]:
        return list(self._snapshot.skills)

    def issues(self) -> list[SkillLoadIssue]:
        return list(self._snapshot.issues)

    def summary_text(self) -> str:
        if not self._snapshot.skills:
            return ""
        lines = ["以下 Skill 可按需通过 LoadSkill 激活："]
        for skill in self._snapshot.skills:
            lines.append(f"- {skill.name}: {skill.description}")
        return "\n".join(lines)

    def create_runtime(self) -> SkillRuntime:
        return SkillRuntime()

    def refresh_one(self, name: str) -> tuple[SkillDefinition | None, SkillLoadIssue | None]:
        previous = self.get(name)
        if previous is None:
            return None, SkillLoadIssue(
                self.loader.project_root / ".dragon-code" / "skills",
                "unknown_skill",
                f"未知 Skill：{name}",
            )
        current, issue = self.loader.reload_one(previous)
        if current != previous:
            skills = tuple(
                current if item.name == current.name else item for item in self._snapshot.skills
            )
            self._snapshot = SkillSnapshot(skills=skills, issues=self._snapshot.issues)
        return current, issue
