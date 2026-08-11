import config
from nodes.base import PipelineState
from nodes.reddit_node import _cache, reddit_node
from tools import reddit

STATE = PipelineState(question="who wins 14469 vs 9295", team_nums=(14469,), season=2022, region="All")


def _clear_cache():
    _cache._store.clear()


def test_disabled_when_no_creds(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_REDDIT", False)
    result = reddit_node(STATE)
    assert result.status == "disabled"


def test_enabled_no_hits_returns_empty(monkeypatch):
    _clear_cache()
    monkeypatch.setattr(config, "ENABLE_REDDIT", True)
    monkeypatch.setattr(reddit, "search_ftc", lambda term, **k: [])

    result = reddit_node(STATE)
    assert result.status == "empty"


def test_enabled_with_hits_renders_text_and_citations(monkeypatch):
    _clear_cache()
    monkeypatch.setattr(config, "ENABLE_REDDIT", True)

    def fake_search(term, **kwargs):
        return [{
            "title": "14469 robot reveal", "selftext_excerpt": "Check it out",
            "url": "https://reddit.com/r/FTC/comments/x/y/", "score": 42, "num_comments": 7,
            "created_utc": 1700000000.0,
        }]

    monkeypatch.setattr(reddit, "search_ftc", fake_search)

    result = reddit_node(STATE)
    assert result.status == "ok"
    assert "14469 robot reveal" in result.text
    assert "42 upvotes" in result.text
    assert result.citations == ("https://reddit.com/r/FTC/comments/x/y/",)


def test_prawcore_exception_becomes_error_status_not_a_crash(monkeypatch):
    _clear_cache()
    monkeypatch.setattr(config, "ENABLE_REDDIT", True)

    def broken_search(term, **kwargs):
        raise ConnectionError("simulated prawcore failure")

    monkeypatch.setattr(reddit, "search_ftc", broken_search)

    result = reddit_node(STATE)  # must not raise
    assert result.status == "error"
    assert "simulated prawcore failure" in result.detail


def test_dedupes_across_multiple_search_terms(monkeypatch):
    _clear_cache()
    monkeypatch.setattr(config, "ENABLE_REDDIT", True)

    same_post = {
        "title": "Same post", "selftext_excerpt": "text", "url": "https://reddit.com/r/FTC/comments/x/y/",
        "score": 1, "num_comments": 0, "created_utc": 0,
    }
    monkeypatch.setattr(reddit, "search_ftc", lambda term, **k: [same_post])

    state = PipelineState(
        question="x", team_nums=(14469,), season=2022, region="All", team_names=("HOW",),
    )
    result = reddit_node(state)
    assert result.text.count("Same post") == 1


def test_second_call_uses_cache(monkeypatch):
    _clear_cache()
    monkeypatch.setattr(config, "ENABLE_REDDIT", True)
    calls = []

    def counting_search(term, **kwargs):
        calls.append(term)
        return [{
            "title": "T", "selftext_excerpt": "b", "url": "https://reddit.com/r/FTC/comments/x/y/",
            "score": 1, "num_comments": 0, "created_utc": 0,
        }]

    monkeypatch.setattr(reddit, "search_ftc", counting_search)

    reddit_node(STATE)
    reddit_node(STATE)

    assert len(calls) == 1
