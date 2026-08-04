import asyncio

import pytest

from dragon_code.permissions import ApprovalChoice
from dragon_code.permissions.approval import ApprovalController


async def test_begin_and_resolve():
    controller = ApprovalController()
    future = controller.begin("call-1")
    controller.resolve("call-1", ApprovalChoice.ALLOW_ONCE)
    assert await future is ApprovalChoice.ALLOW_ONCE


async def test_wrong_id_and_duplicate_answer_are_ignored():
    controller = ApprovalController()
    future = controller.begin("call-1")
    controller.resolve("other", ApprovalChoice.DENY_ONCE)
    assert not future.done()
    controller.resolve("call-1", ApprovalChoice.ALLOW_ALWAYS)
    controller.resolve("call-1", ApprovalChoice.DENY_ONCE)
    assert await future is ApprovalChoice.ALLOW_ALWAYS


async def test_cancel_wakes_waiter_without_leak():
    controller = ApprovalController()
    future = controller.begin("call-1")
    controller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await future


async def test_only_one_request_can_wait():
    controller = ApprovalController()
    controller.begin("call-1")
    with pytest.raises(RuntimeError):
        controller.begin("call-2")
    controller.cancel()
