import json
from pathlib import Path

import pytest
import requests

from tools import discourse

FIXTURES = Path(__file__).parent.parent / "fixtures" / "chiefdelphi"


def _raw_response(fname: str) -> dict:
    """The recorded fixture is discourse.search's already-parsed OUTPUT, not
    the raw Discourse response -- these tests exercise search() itself, so
    they need the raw {"posts": [...], "topics": [...]} shape it parses.
    We reconstruct a minimal raw payload from the recorded output plus a
    hand-written raw sample for shape coverage."""
    with open(FIXTURES / fname, encoding="utf-8") as f:
        return json.load(f)


RAW_HIT = {
    "posts": [
        {
            "id": 3733967, "name": "Zakk Jackson", "username": "Zakk_J",
            "avatar_template": "/x/{size}/1.png", "created_at": "2025-09-08T17:00:47.599Z",
            "like_count": 1, "blurb": "So one thing I've been trying to figure out...",
            "post_number": 1, "topic_id": 506102,
        },
        {
            "id": 3733968, "name": "No Topic", "username": "orphan_user",
            "avatar_template": "/x/{size}/2.png", "created_at": "2025-09-08T18:00:00.000Z",
            "like_count": 0, "blurb": "This post's topic is missing from the response.",
            "post_number": 1, "topic_id": 999999,
        },
    ],
    "topics": [
        {
            "id": 506102, "title": "FTC Decode Base Strategy", "fancy_title": "FTC Decode Base Strategy",
            "slug": "ftc-decode-base-strategy", "category_id": 5, "posts_count": 12,
        },
    ],
}

RAW_EMPTY = {"posts": [], "topics": [], "users": [], "categories": [], "tags": [], "groups": []}


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code != 200:
            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        return self._payload


def test_search_parses_posts_joined_to_topics(monkeypatch):
    monkeypatch.setattr("tools.http.get", lambda *a, **k: _FakeResponse(RAW_HIT))

    results = discourse.search("14469 FTC")

    assert len(results) == 1  # the orphan post (missing topic) is dropped
    assert results[0]["title"] == "FTC Decode Base Strategy"
    assert results[0]["username"] == "Zakk_J"
    assert results[0]["url"] == "https://www.chiefdelphi.com/t/ftc-decode-base-strategy/506102/1"


def test_search_empty_result_returns_empty_list(monkeypatch):
    monkeypatch.setattr("tools.http.get", lambda *a, **k: _FakeResponse(RAW_EMPTY))

    assert discourse.search("some team with no chief delphi presence") == []


def test_search_respects_limit(monkeypatch):
    many_posts = [dict(RAW_HIT["posts"][0], id=i, post_number=i) for i in range(1, 11)]
    monkeypatch.setattr(
        "tools.http.get", lambda *a, **k: _FakeResponse({"posts": many_posts, "topics": RAW_HIT["topics"]}),
    )

    results = discourse.search("popular term", limit=3)
    assert len(results) == 3


def test_search_raises_on_http_error(monkeypatch):
    monkeypatch.setattr("tools.http.get", lambda *a, **k: _FakeResponse({}, status_code=500))

    with pytest.raises(requests.HTTPError):
        discourse.search("anything")


def test_search_term_passed_via_params_not_interpolated(monkeypatch):
    """The search host is a fixed constant and `term` must go through
    `params=` (URL-encoded), never string-interpolated into the URL --
    otherwise a crafted question could redirect the request elsewhere."""
    captured = {}

    def fake_get(url, *, params=None, timeout=None, **kwargs):
        captured["url"] = url
        captured["params"] = params
        return _FakeResponse(RAW_EMPTY)

    monkeypatch.setattr("tools.http.get", fake_get)

    discourse.search("14469 FTC; DROP TABLE topics; --")

    assert captured["url"] == discourse.SEARCH_URL
    assert captured["params"] == {"term": "14469 FTC; DROP TABLE topics; --"}


def test_recorded_fixture_shape_matches_search_output():
    """Sanity check on the committed fixture (recorded via
    scripts/record_fixtures.py --chief-delphi) -- it's search()'s parsed
    output, so every entry must already have search's exact keys."""
    results = _raw_response("ftc_decode_strategy.json")
    assert results
    for entry in results:
        assert set(entry.keys()) == {"title", "blurb", "url", "username", "created_at"}
        assert entry["url"].startswith("https://www.chiefdelphi.com/t/")
