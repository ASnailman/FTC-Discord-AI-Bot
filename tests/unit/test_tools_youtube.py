import pytest

from tools import youtube
from youtube_transcript_api import (
    InvalidVideoId,
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
)


class _FakeDDGSResults:
    def __init__(self, results):
        self._results = results

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def text(self, query, max_results=None):
        return self._results[:max_results] if max_results else list(self._results)


# --- find_video_ids ---

def test_find_video_ids_extracts_watch_url_ids(monkeypatch):
    results = [{"href": "https://www.youtube.com/watch?v=Rbu7QiIYTd0", "title": "reveal"}]
    monkeypatch.setattr(youtube, "DDGS", lambda: _FakeDDGSResults(results))

    ids = youtube.find_video_ids("14469 FTC robot reveal")
    assert ids == ["Rbu7QiIYTd0"]


def test_find_video_ids_extracts_shorts_url_ids(monkeypatch):
    results = [{"href": "https://www.youtube.com/shorts/hGcbAIwTj1Q", "title": "short"}]
    monkeypatch.setattr(youtube, "DDGS", lambda: _FakeDDGSResults(results))

    ids = youtube.find_video_ids("x")
    assert ids == ["hGcbAIwTj1Q"]


def test_find_video_ids_extracts_youtu_be_short_links(monkeypatch):
    results = [{"href": "https://youtu.be/Rbu7QiIYTd0", "title": "short link"}]
    monkeypatch.setattr(youtube, "DDGS", lambda: _FakeDDGSResults(results))

    ids = youtube.find_video_ids("x")
    assert ids == ["Rbu7QiIYTd0"]


def test_find_video_ids_ignores_non_youtube_urls(monkeypatch):
    results = [{"href": "https://www.chiefdelphi.com/t/some-post/1", "title": "not youtube"}]
    monkeypatch.setattr(youtube, "DDGS", lambda: _FakeDDGSResults(results))

    assert youtube.find_video_ids("x") == []


def test_find_video_ids_dedupes(monkeypatch):
    results = [
        {"href": "https://www.youtube.com/watch?v=Rbu7QiIYTd0"},
        {"href": "https://www.youtube.com/watch?v=Rbu7QiIYTd0"},
    ]
    monkeypatch.setattr(youtube, "DDGS", lambda: _FakeDDGSResults(results))

    ids = youtube.find_video_ids("x", max_results=5)
    assert ids == ["Rbu7QiIYTd0"]


def test_find_video_ids_respects_max_results(monkeypatch):
    results = [
        {"href": f"https://www.youtube.com/watch?v=vid0000000{i}"} for i in range(5)
    ]
    monkeypatch.setattr(youtube, "DDGS", lambda: _FakeDDGSResults(results))

    ids = youtube.find_video_ids("x", max_results=2)
    assert len(ids) <= 2


def test_find_video_ids_search_failure_returns_empty_list(monkeypatch):
    def broken_ddgs():
        raise ConnectionError("simulated search outage")

    monkeypatch.setattr(youtube, "DDGS", broken_ddgs)

    assert youtube.find_video_ids("x") == []


def test_find_video_ids_rejects_malformed_ids_from_untrusted_search_results(monkeypatch):
    """A crafted/short/malformed 'id' embedded in a search-result URL must
    never survive extraction -- it's used to build a fetch call downstream."""
    results = [
        {"href": "https://www.youtube.com/watch?v=short"},  # too short
        {"href": "https://www.youtube.com/watch?v=has spaces!"},  # invalid chars
        {"href": "https://www.youtube.com/watch?v=Rbu7QiIYTd0"},  # valid
    ]
    monkeypatch.setattr(youtube, "DDGS", lambda: _FakeDDGSResults(results))

    ids = youtube.find_video_ids("x", max_results=5)
    assert ids == ["Rbu7QiIYTd0"]


# --- fetch_transcript ---

class _FakeSnippet:
    def __init__(self, text):
        self.text = text


class _FakeFetchApi:
    def __init__(self, transcript_or_exc):
        self._t = transcript_or_exc

    def fetch(self, video_id, languages=("en",)):
        if isinstance(self._t, Exception):
            raise self._t
        return self._t


def test_fetch_transcript_joins_snippets(monkeypatch):
    monkeypatch.setattr(
        youtube, "YouTubeTranscriptApi",
        lambda: _FakeFetchApi([_FakeSnippet("Hello"), _FakeSnippet("world")]),
    )
    text = youtube.fetch_transcript("Rbu7QiIYTd0", max_chars=1000)
    assert text == "Hello world"


def test_fetch_transcript_truncates_to_max_chars(monkeypatch):
    monkeypatch.setattr(
        youtube, "YouTubeTranscriptApi", lambda: _FakeFetchApi([_FakeSnippet("x" * 1000)]),
    )
    text = youtube.fetch_transcript("Rbu7QiIYTd0", max_chars=50)
    assert len(text) == 50


def test_fetch_transcript_rejects_non_id_input():
    """A malformed id must never even attempt a fetch call."""
    assert youtube.fetch_transcript("not-a-real-id!!", max_chars=1000) == ""
    assert youtube.fetch_transcript("short", max_chars=1000) == ""
    assert youtube.fetch_transcript("", max_chars=1000) == ""


_EXCEPTION_FACTORIES = {
    "TranscriptsDisabled": lambda: TranscriptsDisabled("Rbu7QiIYTd0"),
    "NoTranscriptFound": lambda: NoTranscriptFound("Rbu7QiIYTd0", ("en",), []),
    "VideoUnavailable": lambda: VideoUnavailable("Rbu7QiIYTd0"),
    "RequestBlocked": lambda: RequestBlocked("Rbu7QiIYTd0"),
    "IpBlocked": lambda: IpBlocked("Rbu7QiIYTd0"),
    "InvalidVideoId": lambda: InvalidVideoId("Rbu7QiIYTd0"),
}


@pytest.mark.parametrize("exc_name", list(_EXCEPTION_FACTORIES))
def test_fetch_transcript_every_documented_error_becomes_empty_string(monkeypatch, exc_name):
    exc = _EXCEPTION_FACTORIES[exc_name]()
    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", lambda: _FakeFetchApi(exc))

    assert youtube.fetch_transcript("Rbu7QiIYTd0", max_chars=1000) == ""
