"""Root pytest configuration.

Two guarantees enforced here:
1. Tests marked ``live`` never run unless the caller explicitly asked for them
   (``-m live``) AND a Gemini key is configured. A bare ``pytest`` invocation
   is always network-free and never fails on a missing secret.
2. Every other test is prevented from making a real network call, even by
   accident (e.g. a refactor that forgets to inject a fixture/mock).
"""
import os

import pytest


def pytest_collection_modifyitems(config, items):
    selected_live = "live" in (config.getoption("-m") or "")
    have_key = bool(os.getenv("GOOGLE_API_KEY"))
    skip_live = pytest.mark.skip(
        reason="live test: pass `-m live` and set GOOGLE_API_KEY to run"
    )
    for item in items:
        if "live" in item.keywords and not (selected_live and have_key):
            item.add_marker(skip_live)


@pytest.fixture(autouse=True)
def _block_network(request, monkeypatch):
    """Offline tests may never hit the network. `live`-marked tests are exempt."""
    if "live" in request.keywords:
        yield
        return

    def _raise(*args, **kwargs):
        raise AssertionError(
            "an offline test attempted a network call via `requests` — "
            "mark it `live` or inject a fixture/mock instead"
        )

    monkeypatch.setattr("requests.post", _raise, raising=False)
    monkeypatch.setattr("requests.get", _raise, raising=False)
    monkeypatch.setattr("requests.sessions.Session.request", _raise, raising=False)
    yield
