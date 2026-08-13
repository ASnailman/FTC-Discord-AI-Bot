"""Per-user daily quota and process-wide concurrency cap for /portfolio.

Three independent layers of abuse/cost control across this feature (see
docs/security.md):

1. `app_commands.checks.cooldown` in bot.py -- Discord-enforced, blocks
   rapid re-invocation by the same user.
2. `DailyQuota` here -- a rolling 24h window per user, so a user can't
   simply wait out the cooldown and grind through many generations (each
   one costs several Gemini calls) in a day.
3. `concurrency_semaphore()` here -- a process-wide cap on how many
   generations run at once, so a burst of legitimate requests can't pile
   up concurrent Gemini calls and memory (rendering pages, holding
   uploaded images) all at the same time.

`DailyQuota` is a plain dict of timestamps per user, pruned lazily under a
lock -- not a new dependency, following `tools.cache.TTLCache`'s reasoning
that this is small, in-process, best-effort state, not something that
needs a real store.
"""
import asyncio
import time
from collections import defaultdict
from threading import Lock

import config

_DAY_SECONDS = 24 * 60 * 60


class QuotaExceededError(Exception):
    """Raised by `DailyQuota.check_and_consume` once a user is over their
    daily limit. `retry_after_seconds` is safe to show the user directly."""

    def __init__(self, retry_after_seconds: float):
        super().__init__(f"daily portfolio quota exceeded, retry after {retry_after_seconds:.0f}s")
        self.retry_after_seconds = retry_after_seconds


class DailyQuota:
    def __init__(self, limit: int, window_seconds: float = _DAY_SECONDS):
        self.limit = limit
        self.window_seconds = window_seconds
        self._usage: dict[int, list[float]] = defaultdict(list)
        self._lock = Lock()

    def check_and_consume(self, user_id: int) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            fresh = [t for t in self._usage[user_id] if t > cutoff]
            if len(fresh) >= self.limit:
                retry_after = max(0.0, self.window_seconds - (now - fresh[0]))
                self._usage[user_id] = fresh
                raise QuotaExceededError(retry_after)
            fresh.append(now)
            self._usage[user_id] = fresh

    def remaining(self, user_id: int) -> int:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            fresh = [t for t in self._usage[user_id] if t > cutoff]
            return max(0, self.limit - len(fresh))


_daily_quota = DailyQuota(limit=config.PORTFOLIO_DAILY_QUOTA)
_concurrency_semaphore = asyncio.Semaphore(config.PORTFOLIO_MAX_CONCURRENT)


def check_and_consume_daily_quota(user_id: int) -> None:
    _daily_quota.check_and_consume(user_id)


def concurrency_semaphore() -> asyncio.Semaphore:
    return _concurrency_semaphore
