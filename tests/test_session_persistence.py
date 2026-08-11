"""会话 JSONL 编解码、读写、恢复和清理测试。"""

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import pytest

from dragon_code.models import ChatMessage, ToolCall, ToolResult
from dragon_code.sessions.codec import (
    SessionRecordError,
    compact_record,
    message_to_record,
    record_to_message,
)
from dragon_code.sessions.manager import SessionManager
from dragon_code.sessions.models import RestoredSession, SessionInfo
from dragon_code.sessions.reader import SessionReader
from dragon_code.sessions.writer import SessionWriter


def read_json_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_models_store_complete_metadata(tmp_path: Path):
    info = SessionInfo("id", "title", datetime.now(), "model", 10, tmp_path / "x")
    restored = RestoredSession("id", [], "model", 1, 2, True)

    assert info.file_size == 10
    assert restored.skipped_lines == 2
    assert restored.orphan_call_truncated is True


def test_basic_message_codec_round_trip():
    message = ChatMessage("assistant", "你好")

    record = message_to_record(message, 123, "dragon-model")

    assert record["model"] == "dragon-model"
    assert record["timestamp"] == 123
    assert record_to_message(record) == message


def test_tool_and_hidden_blocks_codec_round_trip():
    message = ChatMessage(
        role="assistant",
        content="读取中",
        tool_calls=[ToolCall("toolu_1", "Read", {"path": "a.py"}, '{"path":', "")],
        tool_results=[
            ToolResult(
                "toolu_1",
                "Read",
                False,
                content="partial",
                error_code="not_found",
                error_message="missing",
                metadata={"path": "a.py"},
                truncated=True,
            )
        ],
        hidden_blocks=[{"type": "thinking", "thinking": "hidden", "signature": "sig"}],
    )

    restored = record_to_message(message_to_record(message, 123))

    assert restored == message


def test_codec_rejects_wrong_field_types():
    record = message_to_record(ChatMessage("user", "x"), 1)
    record["tool_calls"] = "bad"

    with pytest.raises(SessionRecordError):
        record_to_message(record)


def test_compact_record_has_clear_type():
    assert compact_record(42) == {"type": "compact", "timestamp": 42}


def test_writer_appends_valid_json_and_model_only_once(tmp_path: Path):
    path = tmp_path / "session" / "conversation.jsonl"
    writer = SessionWriter(path, "deepseek")

    writer.append(ChatMessage("user", "问题"))
    writer.append(ChatMessage("assistant", "回答"))
    writer.close()
    records = read_json_lines(path)

    assert [record["role"] for record in records] == ["user", "assistant"]
    assert records[0]["model"] == "deepseek"
    assert "model" not in records[1]
    assert all(isinstance(record["timestamp"], int) for record in records)


def test_writer_replace_appends_compact_and_new_history(tmp_path: Path):
    path = tmp_path / "conversation.jsonl"
    writer = SessionWriter(path, "model")
    writer.append(ChatMessage("user", "旧历史"))
    writer.replace([ChatMessage("user", "摘要后的历史")])
    writer.close()

    records = read_json_lines(path)

    assert [record["type"] for record in records] == ["message", "compact", "message"]
    assert records[-1]["content"] == "摘要后的历史"


def test_writer_close_is_idempotent_and_rejects_append(tmp_path: Path):
    writer = SessionWriter(tmp_path / "conversation.jsonl", "model")
    writer.close()
    writer.close()

    with pytest.raises(RuntimeError, match="已经关闭"):
        writer.append(ChatMessage("user", "x"))


def test_reader_skips_bad_and_partial_lines(tmp_path: Path):
    path = tmp_path / "conversation.jsonl"
    good = json.dumps(message_to_record(ChatMessage("user", "保留"), 10, "model"))
    path.write_text(f'{good}\nnot-json\n{{"role":', encoding="utf-8")

    restored = SessionReader().read(path, "20260811-120000-abcd")

    assert restored.messages == [ChatMessage("user", "保留")]
    assert restored.skipped_lines == 2
    assert restored.model == "model"


def test_reader_uses_messages_after_last_compact(tmp_path: Path):
    path = tmp_path / "conversation.jsonl"
    records = [
        message_to_record(ChatMessage("user", "old"), 1, "model"),
        compact_record(2),
        message_to_record(ChatMessage("user", "middle"), 3),
        compact_record(4),
        message_to_record(ChatMessage("user", "new"), 5),
    ]
    path.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")

    restored = SessionReader().read(path, "20260811-120000-abcd")

    assert restored.messages == [ChatMessage("user", "new")]
    assert restored.model == "model"
    assert restored.last_timestamp == 5


def test_reader_truncates_orphan_assistant_tool_call(tmp_path: Path):
    path = tmp_path / "conversation.jsonl"
    messages = [
        ChatMessage("user", "read"),
        ChatMessage("assistant", tool_calls=[ToolCall("c1", "Read", {"path": "a"})]),
    ]
    path.write_text(
        "".join(
            json.dumps(message_to_record(message, index)) + "\n"
            for index, message in enumerate(messages, 1)
        ),
        encoding="utf-8",
    )

    restored = SessionReader().read(path, "20260811-120000-abcd")

    assert restored.messages == [ChatMessage("user", "read")]
    assert restored.orphan_call_truncated is True


def test_reader_keeps_complete_multiple_tool_pair(tmp_path: Path):
    path = tmp_path / "conversation.jsonl"
    messages = [
        ChatMessage("user", "read"),
        ChatMessage(
            "assistant",
            tool_calls=[
                ToolCall("c1", "Read", {"path": "a"}),
                ToolCall("c2", "Read", {"path": "b"}),
            ],
        ),
        ChatMessage(
            "tool",
            tool_results=[
                ToolResult("c1", "Read", True, "a"),
                ToolResult("c2", "Read", True, "b"),
            ],
        ),
        ChatMessage("assistant", "done"),
    ]
    path.write_text(
        "".join(
            json.dumps(message_to_record(message, index)) + "\n"
            for index, message in enumerate(messages, 1)
        ),
        encoding="utf-8",
    )

    restored = SessionReader().read(path, "20260811-120000-abcd")

    assert restored.messages == messages
    assert restored.orphan_call_truncated is False


def test_manager_opens_new_session_with_shared_id(tmp_path: Path):
    manager = SessionManager(tmp_path)
    active = manager.open_new("model")

    assert re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{4}", active.session_id)
    active.conversation.commit_messages([ChatMessage("user", "hello")])
    expected = tmp_path / ".dragon-code" / "sessions" / active.session_id
    assert active.writer.jsonl_path == expected / "conversation.jsonl"
    assert expected / "tool-results" == expected / "tool-results"
    manager.close()


def create_session(
    root: Path,
    session_id: str,
    messages: list[ChatMessage],
    model: str = "model",
) -> Path:
    path = root / ".dragon-code" / "sessions" / session_id / "conversation.jsonl"
    writer = SessionWriter(path, model)
    for message in messages:
        writer.append(message)
    writer.close()
    return path


def test_manager_lists_new_sessions_with_metadata(tmp_path: Path):
    first = create_session(
        tmp_path,
        "20260811-120000-aaaa",
        [ChatMessage("user", "A " * 40)],
        "model-a",
    )
    second = create_session(
        tmp_path,
        "20260811-120001-bbbb",
        [ChatMessage("user", "second title")],
        "model-b",
    )
    os.utime(first, (10, 10))
    os.utime(second, (20, 20))
    first_records = read_json_lines(first)
    second_records = read_json_lines(second)
    first_records[0]["timestamp"] = 10
    second_records[0]["timestamp"] = 20
    first.write_text(json.dumps(first_records[0]) + "\n", encoding="utf-8")
    second.write_text(json.dumps(second_records[0]) + "\n", encoding="utf-8")
    (tmp_path / ".dragon-code" / "sessions" / "123-deadbeef").mkdir()

    sessions = SessionManager(tmp_path).list_sessions()

    assert [item.session_id for item in sessions] == [
        "20260811-120001-bbbb",
        "20260811-120000-aaaa",
    ]
    assert sessions[0].title == "second title"
    assert len(sessions[1].title) == 50
    assert sessions[0].model == "model-b"
    assert sessions[0].file_size > 0


def test_manager_restore_continues_original_jsonl(tmp_path: Path):
    session_id = "20260811-120000-abcd"
    path = create_session(tmp_path, session_id, [ChatMessage("user", "old")], "old-model")
    manager = SessionManager(tmp_path)

    active = manager.restore(session_id, "current-model")
    active.conversation.commit_messages([ChatMessage("assistant", "new")])
    manager.close()
    records = read_json_lines(path)

    assert [record["content"] for record in records] == ["old", "new"]
    assert records[0]["model"] == "old-model"
    assert "model" not in records[1]


def test_restore_adds_six_hour_reminder_only_in_memory(tmp_path: Path):
    session_id = "20260811-120000-abcd"
    path = create_session(tmp_path, session_id, [ChatMessage("assistant", "old")])
    records = read_json_lines(path)
    records[0]["timestamp"] = int(time.time()) - 7 * 60 * 60
    path.write_text(json.dumps(records[0]) + "\n", encoding="utf-8")
    before = path.read_text(encoding="utf-8")

    manager = SessionManager(tmp_path)
    active = manager.restore(session_id, "current")

    assert "超过 6 小时" in active.conversation.get_messages()[-1].content
    assert path.read_text(encoding="utf-8") == before
    manager.close()


def test_cleanup_deletes_only_expired_new_sessions(tmp_path: Path):
    manager = SessionManager(tmp_path)
    old_id = "20260101-000000-aaaa"
    recent_id = "20260801-000000-bbbb"
    legacy_id = "1234567890-deadbeef"
    for session_id in [old_id, recent_id, legacy_id]:
        directory = tmp_path / ".dragon-code" / "sessions" / session_id
        directory.mkdir(parents=True)
    old_time = time.time() - 46 * 24 * 60 * 60
    recent_time = time.time() - 44 * 24 * 60 * 60
    os.utime(tmp_path / ".dragon-code" / "sessions" / old_id, (old_time, old_time))
    os.utime(tmp_path / ".dragon-code" / "sessions" / recent_id, (recent_time, recent_time))
    os.utime(tmp_path / ".dragon-code" / "sessions" / legacy_id, (old_time, old_time))

    deleted = manager.cleanup_expired(45)

    assert deleted == [old_id]
    assert not (tmp_path / ".dragon-code" / "sessions" / old_id).exists()
    assert (tmp_path / ".dragon-code" / "sessions" / recent_id).exists()
    assert (tmp_path / ".dragon-code" / "sessions" / legacy_id).exists()


def test_cleanup_uses_last_message_time_not_old_directory_time(tmp_path: Path):
    session_id = "20260101-000000-aaaa"
    path = create_session(tmp_path, session_id, [ChatMessage("user", "recent")])
    directory = path.parent
    old_time = time.time() - 100 * 24 * 60 * 60
    os.utime(directory, (old_time, old_time))

    deleted = SessionManager(tmp_path).cleanup_expired(45)

    assert deleted == []
    assert directory.exists()
