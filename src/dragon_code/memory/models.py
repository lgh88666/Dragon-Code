"""自动记忆操作模型。"""

from dataclasses import dataclass

VALID_ACTIONS = {"create", "update", "delete"}
VALID_LEVELS = {"project", "user"}
VALID_MEMORY_TYPES = {
    "user_preference",
    "correction_feedback",
    "project_knowledge",
    "reference_material",
}


@dataclass
class MemoryOperation:
    """LLM 建议的一次受限记忆文件操作。"""

    action: str
    level: str
    memory_type: str = ""
    title: str = ""
    slug: str = ""
    filename: str = ""
    content: str = ""


@dataclass
class MemoryInfo:
    """记忆管理界面使用的一条只读记录。"""

    level: str
    filename: str
    memory_type: str
    title: str
    content: str
