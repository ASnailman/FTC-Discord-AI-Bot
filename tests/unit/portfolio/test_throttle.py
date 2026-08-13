import asyncio

import pytest

from portfolio.throttle import DailyQuota, QuotaExceededError, concurrency_semaphore


def test_quota_allows_up_to_the_limit():
    quota = DailyQuota(limit=3)
    for _ in range(3):
        quota.check_and_consume(user_id=1)  # must not raise


def test_quota_blocks_the_call_over_the_limit():
    quota = DailyQuota(limit=2)
    quota.check_and_consume(user_id=1)
    quota.check_and_consume(user_id=1)
    with pytest.raises(QuotaExceededError):
        quota.check_and_consume(user_id=1)


def test_quota_is_tracked_independently_per_user():
    quota = DailyQuota(limit=1)
    quota.check_and_consume(user_id=1)
    quota.check_and_consume(user_id=2)  # different user, must not raise


def test_quota_remaining_reflects_usage():
    quota = DailyQuota(limit=3)
    assert quota.remaining(user_id=1) == 3
    quota.check_and_consume(user_id=1)
    assert quota.remaining(user_id=1) == 2


def test_quota_resets_after_the_window_elapses(monkeypatch):
    quota = DailyQuota(limit=1, window_seconds=100)
    t = [1000.0]
    monkeypatch.setattr("time.monotonic", lambda: t[0])

    quota.check_and_consume(user_id=1)
    with pytest.raises(QuotaExceededError):
        quota.check_and_consume(user_id=1)

    t[0] += 101  # past the window
    quota.check_and_consume(user_id=1)  # must not raise


def test_quota_exceeded_error_reports_a_sane_retry_after():
    quota = DailyQuota(limit=1, window_seconds=100)
    quota.check_and_consume(user_id=1)
    with pytest.raises(QuotaExceededError) as exc_info:
        quota.check_and_consume(user_id=1)
    assert 0 <= exc_info.value.retry_after_seconds <= 100


@pytest.mark.anyio
async def test_concurrency_semaphore_bounds_simultaneous_holders():
    sem = asyncio.Semaphore(2)
    active = 0
    max_active = 0
    lock = asyncio.Lock()

    async def worker():
        nonlocal active, max_active
        async with sem:
            async with lock:
                active += 1
                max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            async with lock:
                active -= 1

    await asyncio.gather(*(worker() for _ in range(6)))
    assert max_active <= 2


@pytest.mark.anyio
async def test_module_level_semaphore_is_usable_as_an_async_context_manager():
    async with concurrency_semaphore():
        pass  # must not raise
