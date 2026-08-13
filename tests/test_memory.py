"""自动记忆测试。"""

import asyncio
import json
from pathlib import Path

import pytest

from dragon_code.memory.manager import INDEX_MAX_BYTES, MemoryManager
from dragon_code.memory.models import MemoryOperation
from dragon_code.memory.prompt import build_memory_request
from dragon_code.models import ChatMessage, LLMEvent, ToolCall


class MemoryClient:
    def __init__(self, text: str = "[]", delay: float = 0, fail: bool = False):
        self.text = text
        self.delay = delay
        self.fail = fail
        self.requests = []

    async def stream(self, request):
        self.requests.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("model failed")
        yield LLMEvent(type="text_delta", text=self.text)
        yield LLMEvent(type="completed", message=ChatMessage("assistant", self.text))


def create_operation(**overrides) -> dict:
    operation = {
        "action": "create",
        "level": "user",
        "memory_type": "user_preference",
        "title": "简洁回复",
        "slug": "concise-replies",
        "content": "用户偏好简洁直接的回复。",
    }
    operation.update(overrides)
    return operation


def test_memory_prompt_contains_index_and_has_no_tools():
    request = build_memory_request([ChatMessage("user", "记住它")], "- existing")

    assert request.tools == []
    assert "- existing" in request.messages[0].content
    assert "记住它" in request.messages[0].content
    assert "user_preference" in request.system.stable


def test_should_update_every_fifth_turn_or_keyword(tmp_path: Path):
    manager = MemoryManager(tmp_path, tmp_path / "home")

    assert manager.should_update(4, "普通内容") is False
    assert manager.should_update(5, "普通内容") is True
    assert manager.should_update(1, "请记住这个偏好") is True
    assert manager.should_update(1, "REMEMBER this") is True


def test_load_indexes_project_then_user(tmp_path: Path):
    manager = MemoryManager(tmp_path, tmp_path / "home")
    manager.project_memory_dir.mkdir(parents=True)
    manager.user_memory_dir.mkdir(parents=True)
    (manager.project_memory_dir / "MEMORY.md").write_text("project-line", encoding="utf-8")
    (manager.user_memory_dir / "MEMORY.md").write_text("user-line", encoding="utf-8")

    result = manager.load_indexes()

    assert result.index("project-line") < result.index("user-line")
    assert manager.current_index() == result


async def test_list_read_count_and_delete_memory(tmp_path: Path):
    manager = MemoryManager(tmp_path, tmp_path / "home")
    manager._apply_operations(
        [
            MemoryOperation(
                action="create",
                level="project",
                memory_type="project_knowledge",
                title="项目结构",
                slug="project-layout",
                content="项目使用 src 布局。",
            ),
            MemoryOperation(
                action="create",
                level="user",
                memory_type="user_preference",
                title="回复偏好",
                slug="reply-style",
                content="使用简洁中文。",
            ),
        ]
    )
    manager.load_indexes()

    memories = manager.list_memories()
    assert [(item.level, item.title) for item in memories] == [
        ("project", "项目结构"),
        ("user", "回复偏好"),
    ]
    assert manager.memory_counts() == (1, 1)
    project = manager.read_memory("project", "project_knowledge_project-layout.md")
    assert project.content == "项目使用 src 布局。"

    await manager.delete_memory("project", project.filename)

    assert manager.memory_counts() == (1, 0)
    assert "项目结构" not in manager.current_index()
    assert "回复偏好" in manager.current_index()


async def test_memory_management_rejects_unsafe_targets(tmp_path: Path):
    manager = MemoryManager(tmp_path, tmp_path / "home")

    with pytest.raises(ValueError, match="层级"):
        manager.read_memory("other", "user_preference_test.md")
    with pytest.raises(ValueError, match="不安全"):
        await manager.delete_memory("project", "../outside.md")


def test_combined_index_is_limited_and_marked(tmp_path: Path):
    manager = MemoryManager(tmp_path, tmp_path / "home")
    manager.project_memory_dir.mkdir(parents=True)
    manager.user_memory_dir.mkdir(parents=True)
    lines = "\n".join(f"- 第{i}条 " + "龙" * 200 for i in range(200))
    (manager.project_memory_dir / "MEMORY.md").write_text(lines, encoding="utf-8")
    (manager.user_memory_dir / "MEMORY.md").write_text(lines, encoding="utf-8")

    result = manager.load_indexes()

    assert len(result.encode("utf-8")) <= INDEX_MAX_BYTES
    assert result.endswith("(index truncated)")


def test_parse_operations_accepts_code_fence_and_normalizes_level(tmp_path: Path):
    manager = MemoryManager(tmp_path, tmp_path / "home")
    text = "```json\n" + json.dumps([create_operation(level="project")]) + "\n```"

    operations = manager._parse_operations(text)

    assert len(operations) == 1
    assert operations[0].level == "user"


@pytest.mark.parametrize(
    "filename",
    ["../secret.md", "C:/secret.md", "MEMORY.md", "bad.txt", "x/y.md"],
)
def test_parse_operations_rejects_unsafe_filename(tmp_path: Path, filename: str):
    manager = MemoryManager(tmp_path, tmp_path / "home")
    text = json.dumps([{"action": "delete", "level": "user", "filename": filename}])

    assert manager._parse_operations(text) == []


def test_apply_create_update_delete_rebuilds_index(tmp_path: Path):
    manager = MemoryManager(tmp_path, tmp_path / "home")
    create = manager._parse_operations(json.dumps([create_operation()]))
    manager._apply_operations(create)
    note = manager.user_memory_dir / "user_preference_concise-replies.md"

    assert note.is_file()
    assert "type: user_preference" in note.read_text(encoding="utf-8")
    assert "简洁回复" in (manager.user_memory_dir / "MEMORY.md").read_text(encoding="utf-8")

    update = manager._parse_operations(
        json.dumps(
            [
                {
                    "action": "update",
                    "level": "user",
                    "filename": note.name,
                    "title": "更简洁",
                    "content": "只说重点。",
                }
            ]
        )
    )
    manager._apply_operations(update)
    assert "更简洁" in note.read_text(encoding="utf-8")
    assert "只说重点" in (manager.user_memory_dir / "MEMORY.md").read_text(encoding="utf-8")

    delete = manager._parse_operations(
        json.dumps([{"action": "delete", "level": "user", "filename": note.name}])
    )
    manager._apply_operations(delete)
    assert not note.exists()
    assert "更简洁" not in (manager.user_memory_dir / "MEMORY.md").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_schedule_update_runs_in_background_and_refreshes_index(tmp_path: Path):
    manager = MemoryManager(tmp_path, tmp_path / "home")
    client = MemoryClient(json.dumps([create_operation()]), delay=0.05)

    manager.schedule_update(client, [ChatMessage("user", "记住")], 1, "记住")

    assert manager.current_index() == ""
    await asyncio.sleep(0.1)
    assert "简洁回复" in manager.current_index()
    assert client.requests[0].tools == []
    await manager.close()


@pytest.mark.asyncio
async def test_failed_update_is_silent_and_later_update_can_run(tmp_path: Path, caplog):
    manager = MemoryManager(tmp_path, tmp_path / "home")
    failed = MemoryClient(fail=True)
    manager.schedule_update(failed, [ChatMessage("user", "记住")], 1, "记住")
    await asyncio.sleep(0.02)

    successful = MemoryClient(json.dumps([create_operation()]))
    manager.schedule_update(successful, [ChatMessage("user", "记住")], 2, "记住")
    await asyncio.sleep(0.02)

    assert "简洁回复" in manager.current_index()
    assert "自动记忆更新失败" in caplog.text
    await manager.close()


@pytest.mark.asyncio
async def test_memory_response_with_tool_call_is_rejected(tmp_path: Path, caplog):
    class ToolCallingClient:
        async def stream(self, request):
            yield LLMEvent(
                type="completed",
                message=ChatMessage(
                    "assistant",
                    tool_calls=[ToolCall("c1", "Read", {"path": "x"})],
                ),
            )

    manager = MemoryManager(tmp_path, tmp_path / "home")
    manager.schedule_update(ToolCallingClient(), [ChatMessage("user", "记住")], 1, "记住")
    await asyncio.sleep(0.02)

    assert manager.current_index() == ""
    assert "自动记忆更新失败" in caplog.text
    await manager.close()


@pytest.mark.asyncio
async def test_close_cancels_pending_tasks(tmp_path: Path):
    manager = MemoryManager(tmp_path, tmp_path / "home")
    manager.schedule_update(
        MemoryClient(json.dumps([create_operation()]), delay=10),
        [ChatMessage("user", "记住")],
        1,
        "记住",
    )

    await manager.close()

    assert manager._tasks == set()
