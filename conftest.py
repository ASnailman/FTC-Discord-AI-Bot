"""Root pytest configuration.

Three guarantees enforced here:
1. Tests marked ``live`` never run unless the caller explicitly asked for them
   (``-m live``) AND a Gemini key is configured. A bare ``pytest`` invocation
   is always network-free and never fails on a missing secret.
2. Tests marked ``external`` (Chief Delphi/Reddit/YouTube) never run unless
   the caller passes ``-m external``. Unlike ``live``, no API key is
   required -- Chief Delphi needs no auth, and the other two self-skip via
   their own node-level flag checks if unconfigured.
3. Every other test is prevented from making a real network call, even by
   accident (e.g. a refactor that forgets to inject a fixture/mock). This
   covers `requests` (FTCScout, Chief Delphi, praw/prawcore),  `httpx` (the
   transport `langchain_google_genai`'s `google-genai` SDK uses for Gemini
   -- confirmed during development that an offline test calling
   `nodes.router.route` with `ENABLE_LLM_ROUTER` left on could otherwise
   silently make a REAL, billed Gemini call, since it doesn't go through
   `requests` at all), and `primp` (the native Rust HTTP client `ddgs`
   defaults to -- also not `requests` or `httpx`). `youtube-transcript-api`
   uses `requests` internally, so it's already covered by the first patch.
"""
import os

import pytest


def pytest_collection_modifyitems(config, items):
    selected_live = "live" in (config.getoption("-m") or "")
    have_key = bool(os.getenv("GOOGLE_API_KEY"))
    skip_live = pytest.mark.skip(
        reason="live test: pass `-m live` and set GOOGLE_API_KEY to run"
    )
    selected_external = "external" in (config.getoption("-m") or "")
    skip_external = pytest.mark.skip(
        reason="external test: hits third-party community APIs; pass `-m external` to run"
    )
    for item in items:
        if "live" in item.keywords and not (selected_live and have_key):
            item.add_marker(skip_live)
        if "external" in item.keywords and not selected_external:
            item.add_marker(skip_external)


@pytest.fixture(autouse=True)
def _block_network(request, monkeypatch):
    """Offline tests may never hit the network. `live`- and `external`-marked
    tests are exempt."""
    if "live" in request.keywords or "external" in request.keywords:
        yield
        return

    def _raise(*args, **kwargs):
        raise AssertionError(
            "an offline test attempted a network call via `requests` — "
            "mark it `live` or inject a fixture/mock instead"
        )

    def _raise_httpx(*args, **kwargs):
        raise AssertionError(
            "an offline test attempted a network call via `httpx` (used by the "
            "Gemini/google-genai client) — mark it `live`/`external` or inject "
            "a fixture/mock instead"
        )

    def _raise_primp(*args, **kwargs):
        raise AssertionError(
            "an offline test attempted a network call via `primp` (ddgs's default "
            "HTTP client) — mark it `external` or inject a fixture/mock instead"
        )

    monkeypatch.setattr("requests.post", _raise, raising=False)
    monkeypatch.setattr("requests.get", _raise, raising=False)
    monkeypatch.setattr("requests.sessions.Session.request", _raise, raising=False)
    monkeypatch.setattr("httpx.Client.send", _raise_httpx, raising=False)
    monkeypatch.setattr("httpx.AsyncClient.send", _raise_httpx, raising=False)
    monkeypatch.setattr("primp.Client.request", _raise_primp, raising=False)
    monkeypatch.setattr("primp.AsyncClient.request", _raise_primp, raising=False)
    yield
