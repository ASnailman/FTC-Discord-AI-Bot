"""A minimal in-process TTL cache for external-source lookups.

External community content (Chief Delphi/Reddit/YouTube results) is never
persisted to ChromaDB -- see docs/adr/0003 -- so repeat questions about the
same team within a session would otherwise re-hit third-party APIs on every
`/ask`. This is deliberately not a new dependency (no `cachetools`,
`diskcache`): it's a plain dict with a monotonic-time expiry check, safe for
the values this module handles (small lists of dicts).
"""
import time
from threading import Lock


class TTLCache:
    def __init__(self, ttl_seconds: float):
        self.ttl_seconds = ttl_seconds
        self._store: dict[str, tuple[float, object]] = {}
        self._lock = Lock()

    def get(self, key: str):
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() >= expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value) -> None:
        with self._lock:
            self._store[key] = (time.monotonic() + self.ttl_seconds, value)
