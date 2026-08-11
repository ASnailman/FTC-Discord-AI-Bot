import config
from nodes.base import PipelineState
from nodes.youtube_node import _cache, youtube_node
from tools import youtube

STATE = PipelineState(question="what's 14469's auto strategy", team_nums=(14469,), season=2022, region="All")


def _clear_cache():
    _cache._store.clear()


def test_disabled_by_default_flag(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_YOUTUBE", False)
    result = youtube_node(STATE)
    assert result.status == "disabled"


def test_enabled_no_videos_found_returns_empty(monkeypatch):
    _clear_cache()
    monkeypatch.setattr(config, "ENABLE_YOUTUBE", True)
    monkeypatch.setattr(youtube, "find_video_ids", lambda term, **k: [])

    result = youtube_node(STATE)
    assert result.status == "empty"


def test_enabled_videos_found_but_no_captions_returns_empty(monkeypatch):
    _clear_cache()
    monkeypatch.setattr(config, "ENABLE_YOUTUBE", True)
    monkeypatch.setattr(youtube, "find_video_ids", lambda term, **k: ["Rbu7QiIYTd0"])
    monkeypatch.setattr(youtube, "fetch_transcript", lambda vid, **k: "")

    result = youtube_node(STATE)
    assert result.status == "empty"


def test_enabled_with_transcript_renders_text_and_citation(monkeypatch):
    _clear_cache()
    monkeypatch.setattr(config, "ENABLE_YOUTUBE", True)
    monkeypatch.setattr(youtube, "find_video_ids", lambda term, **k: ["Rbu7QiIYTd0"])
    monkeypatch.setattr(youtube, "fetch_transcript", lambda vid, **k: "Robot uses a four-bar linkage intake.")

    result = youtube_node(STATE)
    assert result.status == "ok"
    assert "four-bar linkage" in result.text
    assert result.citations == ("https://www.youtube.com/watch?v=Rbu7QiIYTd0",)


def test_search_exception_becomes_error_status_not_a_crash(monkeypatch):
    _clear_cache()
    monkeypatch.setattr(config, "ENABLE_YOUTUBE", True)

    def broken_search(term, **kwargs):
        raise RuntimeError("simulated search outage")

    monkeypatch.setattr(youtube, "find_video_ids", broken_search)

    result = youtube_node(STATE)  # must not raise
    assert result.status == "error"
    assert "simulated search outage" in result.detail


def test_dedupes_video_ids_across_search_terms(monkeypatch):
    _clear_cache()
    monkeypatch.setattr(config, "ENABLE_YOUTUBE", True)
    monkeypatch.setattr(youtube, "find_video_ids", lambda term, **k: ["Rbu7QiIYTd0"])
    monkeypatch.setattr(youtube, "fetch_transcript", lambda vid, **k: "commentary text")

    state = PipelineState(
        question="x", team_nums=(14469,), season=2022, region="All", team_names=("HOW",),
    )
    result = youtube_node(state)
    assert result.citations.count("https://www.youtube.com/watch?v=Rbu7QiIYTd0") == 1


def test_second_call_uses_cache_for_both_search_and_transcript(monkeypatch):
    _clear_cache()
    monkeypatch.setattr(config, "ENABLE_YOUTUBE", True)
    search_calls = []
    transcript_calls = []

    def counting_search(term, **kwargs):
        search_calls.append(term)
        return ["Rbu7QiIYTd0"]

    def counting_transcript(vid, **kwargs):
        transcript_calls.append(vid)
        return "text"

    monkeypatch.setattr(youtube, "find_video_ids", counting_search)
    monkeypatch.setattr(youtube, "fetch_transcript", counting_transcript)

    youtube_node(STATE)
    youtube_node(STATE)

    assert len(search_calls) == 1
    assert len(transcript_calls) == 1
