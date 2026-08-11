"""Hits real third-party community APIs. Deselected by default -- pass
`-m external` to run (see conftest.py). Unlike `tests/live/`'s `live`
marker, no GOOGLE_API_KEY is required: Chief Delphi and the YouTube search
need no auth at all (Reddit does -- its live test self-skips without
REDDIT_CLIENT_ID/SECRET, same as the node does at runtime).
"""
import pytest

import config
from tools import discourse, youtube

pytestmark = pytest.mark.external


def test_chief_delphi_search_returns_real_results():
    results = discourse.search("FTC DECODE strategy", limit=5)

    assert isinstance(results, list)
    for entry in results:
        assert entry["url"].startswith("https://www.chiefdelphi.com/t/")
        assert isinstance(entry["title"], str)


def test_chief_delphi_search_handles_no_hits_gracefully():
    # A near-nonsense term is very unlikely to match anything -- this
    # exercises the "empty is a normal outcome" path against the real API.
    results = discourse.search("zzqxvj_no_such_team_zzqxvj", limit=5)
    assert isinstance(results, list)


def test_youtube_find_video_ids_returns_real_ids():
    ids = youtube.find_video_ids("FTC DECODE robot reveal", max_results=2)

    assert isinstance(ids, list)
    for video_id in ids:
        assert youtube._VIDEO_ID_RE.match(video_id)


def test_youtube_fetch_transcript_on_a_real_video_id_does_not_raise():
    ids = youtube.find_video_ids("FTC DECODE robot reveal", max_results=1)
    if not ids:
        pytest.skip("no video ids returned by the search -- nothing to fetch a transcript for")
    text = youtube.fetch_transcript(ids[0], max_chars=1000)
    assert isinstance(text, str)  # "" (no captions) is a valid, expected outcome


@pytest.mark.skipif(not config.ENABLE_REDDIT, reason="REDDIT_CLIENT_ID/SECRET not configured")
def test_reddit_search_returns_real_results():
    from tools import reddit

    results = reddit.search_ftc("robot reveal", limit=5)

    assert isinstance(results, list)
    for entry in results:
        assert entry["url"].startswith("https://reddit.com/r/FTC/")
