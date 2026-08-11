"""上下文状态类型测试。"""

import re
from pathlib import Path

import pytest

from dragon_code.context.constants import (
    AUTO_SAFETY_MARGIN,
    COMPACT_FAILURE_LIMIT,
    PREVIEW_MAX_BYTES,
    PREVIEW_MAX_LINES,
    SINGLE_TOOL_RESULT_BYTES,
    TOOL_RESULTS_MESSAGE_BYTES,
)
from dragon_code.context.state import (
    CompactCircuitBreaker,
    ReplacementDecision,
    ReplacementLedger,
    SessionPaths,
    UsageAnchor,
    is_new_session_id,
    is_safe_session_id,
    make_session_id,
    safe_result_filename,
)


def test_context_constants_match_approved_spec():
    assert SINGLE_TOOL_RESULT_BYTES == 50_000
    assert TOOL_RESULTS_MESSAGE_BYTES == 200_000
    assert PREVIEW_MAX_LINES == 20
    assert PREVIEW_MAX_BYTES == 2_048
    assert AUTO_SAFETY_MARGIN == 13_000
    assert COMPACT_FAILURE_LIMIT == 3


def test_session_id_is_unique_and_windows_safe():
    values = {make_session_id() for _ in range(20)}

    assert len(values) == 20
    assert all(re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{4}", value) for value in values)
    assert all(is_new_session_id(value) for value in values)


def test_legacy_session_id_remains_safe_but_is_not_new():
    assert is_safe_session_id("1234567890-deadbeef") is True
    assert is_new_session_id("1234567890-deadbeef") is False


@pytest.mark.parametrize("value", ["../bad", "x/y", "x\\y", "", "20260811-bad"])
def test_unsafe_session_ids_are_rejected(value: str, tmp_path: Path):
    assert is_safe_session_id(value) is False
    with pytest.raises(ValueError):
        SessionPaths.create(tmp_path, value)


def test_session_paths_stay_under_working_directory(tmp_path: Path):
    paths = SessionPaths.create(tmp_path, "1234567890-deadbeef")

    assert paths.tool_results_dir == (
        tmp_path.resolve() / ".dragon-code" / "sessions" / "1234567890-deadbeef" / "tool-results"
    )
    assert paths.result_path("../CON:<bad>\\id").parent == paths.tool_results_dir


@pytest.mark.parametrize("call_id", ["../x", "..\\x", "CON", "a:b*c?d", "", "中文/调用"])
def test_safe_result_filename_is_stable_and_safe(call_id: str):
    filename = safe_result_filename(call_id)

    assert filename == safe_result_filename(call_id)
    assert re.fullmatch(r"tool-[A-Za-z0-9_-]+-[0-9a-f]{12}\.txt", filename)
    assert "/" not in filename and "\\" not in filename and ".." not in filename


def test_cleaned_prefix_collisions_use_different_hashes():
    assert safe_result_filename("a/b") != safe_result_filename("a\\b")


def test_replacement_ledger_freezes_first_decision(tmp_path: Path):
    ledger = ReplacementLedger()
    first = ReplacementDecision(False)
    later = ReplacementDecision(True, "preview", tmp_path / "result.txt", 100)

    assert ledger.freeze("call-1", first) is first
    assert ledger.freeze("call-1", later) is first
    assert ledger.get("call-1") is first


def test_usage_anchor_update_and_invalidate():
    anchor = UsageAnchor()
    anchor.update(123, 456)

    assert anchor.valid is True
    assert anchor.total_tokens == 123
    assert anchor.covered_chars == 456

    anchor.invalidate()
    assert anchor.valid is False


def test_usage_anchor_rejects_negative_values():
    with pytest.raises(ValueError):
        UsageAnchor().update(-1, 10)


def test_compact_circuit_breaker_trips_at_three_and_success_resets():
    breaker = CompactCircuitBreaker()

    breaker.record_failure()
    breaker.record_failure()
    assert breaker.tripped is False
    breaker.record_failure()
    assert breaker.tripped is True

    breaker.record_success()
    assert breaker.consecutive_failures == 0
    assert breaker.tripped is False


def test_new_context_state_starts_with_closed_circuit():
    first = CompactCircuitBreaker()
    for _ in range(3):
        first.record_failure()

    second = CompactCircuitBreaker()

    assert first.tripped is True
    assert second.tripped is False
    assert second.consecutive_failures == 0
