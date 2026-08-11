import config
from nodes.base import PipelineState
from nodes.chief_delphi_node import _cache, chief_delphi_node
from tools import discourse

STATE = PipelineState(question="what's 14469's strategy", team_nums=(14469,), season=2022, region="All")


def _clear_cache():
    _cache._store.clear()


def test_disabled_returns_disabled_status(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_CHIEF_DELPHI", False)
    result = chief_delphi_node(STATE)
    assert result.status == "disabled"


def test_enabled_no_hits_returns_empty(monkeypatch):
    _clear_cache()
    monkeypatch.setattr(config, "ENABLE_CHIEF_DELPHI", True)
    monkeypatch.setattr(discourse, "search",lambda term, **k: [])

    result = chief_delphi_node(STATE)
    assert result.status == "empty"
    assert result.text == ""


def test_enabled_with_hits_renders_text_and_citations(monkeypatch):
    _clear_cache()
    monkeypatch.setattr(config, "ENABLE_CHIEF_DELPHI", True)

    def fake_search(term, **kwargs):
        return [{
            "title": "FTC Decode Base Strategy", "blurb": "Ramp-style intake discussion.",
            "url": "https://www.chiefdelphi.com/t/x/1/1", "username": "Zakk_J", "created_at": "2025-09-08",
        }]

    monkeypatch.setattr(discourse, "search",fake_search)

    result = chief_delphi_node(STATE)
    assert result.status == "ok"
    assert "FTC Decode Base Strategy" in result.text
    assert "Zakk_J" in result.text
    assert result.citations == ("https://www.chiefdelphi.com/t/x/1/1",)


def test_discourse_exception_becomes_error_status_not_a_crash(monkeypatch):
    _clear_cache()
    monkeypatch.setattr(config, "ENABLE_CHIEF_DELPHI", True)

    def broken_search(term, **kwargs):
        raise ConnectionError("simulated network failure")

    monkeypatch.setattr(discourse, "search",broken_search)

    result = chief_delphi_node(STATE)  # must not raise
    assert result.status == "error"
    assert "simulated network failure" in result.detail


def test_dedupes_across_multiple_search_terms(monkeypatch):
    _clear_cache()
    monkeypatch.setattr(config, "ENABLE_CHIEF_DELPHI", True)

    same_post = {
        "title": "Same Topic", "blurb": "text", "url": "https://www.chiefdelphi.com/t/x/1/1",
        "username": "u", "created_at": "2025-01-01",
    }
    monkeypatch.setattr(discourse, "search",lambda term, **k: [same_post])

    state = PipelineState(
        question="x", team_nums=(14469,), season=2022, region="All", team_names=("Owlbotics",),
    )
    result = chief_delphi_node(state)
    assert result.text.count("Same Topic") == 1


def test_second_call_uses_cache_not_a_second_search(monkeypatch):
    _clear_cache()
    monkeypatch.setattr(config, "ENABLE_CHIEF_DELPHI", True)
    calls = []

    def counting_search(term, **kwargs):
        calls.append(term)
        return [{
            "title": "T", "blurb": "b", "url": "https://www.chiefdelphi.com/t/x/1/1",
            "username": "u", "created_at": "2025-01-01",
        }]

    monkeypatch.setattr(discourse, "search",counting_search)

    chief_delphi_node(STATE)
    chief_delphi_node(STATE)

    assert len(calls) == 1
