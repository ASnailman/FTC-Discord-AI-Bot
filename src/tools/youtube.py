"""YouTube transcript tool: find candidate video ids via web search, then
fetch closed-caption text for play-by-play robot commentary.

Two independently fail-soft stages -- a search returning no results and a
found video having no captions are different, both-expected outcomes, not
errors. This is the slowest and least reliable of the community sources
(web search plus a second per-video fetch), which is why it's the one node
off by default (`config.ENABLE_YOUTUBE`).
"""
import re

from ddgs import DDGS
from youtube_transcript_api import (
    InvalidVideoId,
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)

# A real YouTube video id is exactly 11 characters from this alphabet.
# Video ids extracted from search results are matched against this before
# ever being used to build a fetch call -- a required input-validation
# boundary (search results are attacker-reachable text), not just cosmetic.
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_URL_ID_RE = re.compile(r"(?:[?&]v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})")

_TRANSCRIPT_ERRORS = (
    TranscriptsDisabled, NoTranscriptFound, VideoUnavailable, RequestBlocked, IpBlocked, InvalidVideoId,
)


def find_video_ids(query: str, *, max_results: int = 2) -> list[str]:
    """Web-searches for YouTube videos matching `query` and returns
    validated, de-duplicated video ids -- never a bare search-result URL.
    Empty list on no results or any search failure; never raises."""
    ids: list[str] = []
    try:
        with DDGS() as ddgs:
            for result in ddgs.text(f"{query} site:youtube.com", max_results=max_results * 3):
                url = result.get("href") or result.get("url") or ""
                match = _URL_ID_RE.search(url)
                if not match:
                    continue
                video_id = match.group(1)
                if _VIDEO_ID_RE.match(video_id) and video_id not in ids:
                    ids.append(video_id)
                if len(ids) >= max_results:
                    break
    except Exception:
        return []
    return ids


def fetch_transcript(video_id: str, *, max_chars: int) -> str:
    """Returns the joined transcript text (English, truncated to
    `max_chars`), or "" for any of: an invalid id, no English captions,
    disabled captions, an unavailable video, or a blocked request. Never
    raises -- every documented failure mode of the underlying API maps to
    an empty string here."""
    if not _VIDEO_ID_RE.match(video_id):
        return ""
    try:
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id, languages=("en",))
    except _TRANSCRIPT_ERRORS:
        return ""
    return " ".join(snippet.text for snippet in fetched)[:max_chars]
