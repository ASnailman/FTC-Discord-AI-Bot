"""Shared HTTP client for the community-source tools (discourse/reddit/youtube).

A single `requests.Session` per process (connection pooling, one place to
set a real User-Agent) plus a small bounded retry for transient failures --
deliberately hand-rolled rather than `urllib3.Retry` to avoid a new
dependency for three call sites.

Every call here must pass an explicit `timeout` <= `config.NODE_TIMEOUT_SECONDS`
so a hung external host can never block past a node's own budget (see
`nodes.base.run_nodes`).
"""
import time
from functools import lru_cache

import requests

USER_AGENT = "ftc-scouting-bot/0.1 (+https://github.com/; research/scouting use)"


@lru_cache(maxsize=1)
def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def get(url: str, *, params: dict = None, timeout: float, max_retries: int = 1, **kwargs) -> requests.Response:
    """GET with a bounded retry on connection/timeout errors only -- never
    retries on a real HTTP error response, since those aren't transient."""
    session = get_session()
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return session.get(url, params=params, timeout=timeout, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt < max_retries:
                time.sleep(0.5 * (attempt + 1))
    raise last_exc
