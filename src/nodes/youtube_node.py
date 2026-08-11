"""YouTube Transcript Node: play-by-play/strategy commentary from robot
reveal or match videos, activated by the router for strategy questions
(see nodes/router.py). Off by default (`config.ENABLE_YOUTUBE`) -- the
slowest, least reliable external source, since it chains a web search with
a per-video caption fetch.
"""
import config
from nodes.base import NodeResult, PipelineState, STATUS_DISABLED, STATUS_EMPTY, STATUS_OK, retrieval_node
from tools import youtube
from tools.cache import TTLCache

_cache = TTLCache(ttl_seconds=config.EXTERNAL_CACHE_TTL_MINUTES * 60)


def _search_terms(state: PipelineState) -> list[str]:
    terms = [f"{t} FTC robot reveal" for t in state.team_nums]
    terms.extend(f"{name} FTC robot reveal" for name in state.team_names)
    return terms or [f"{state.question} FTC"]


def _cached_video_ids(term: str) -> list[str]:
    cache_key = f"youtube_ids:{term}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached
    ids = youtube.find_video_ids(term, max_results=config.YOUTUBE_MAX_VIDEOS)
    _cache.set(cache_key, ids)
    return ids


def _cached_transcript(video_id: str) -> str:
    cache_key = f"youtube_transcript:{video_id}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached
    text = youtube.fetch_transcript(video_id, max_chars=config.MAX_EXTERNAL_CHARS_PER_SOURCE)
    _cache.set(cache_key, text)
    return text


@retrieval_node("youtube")
def youtube_node(state: PipelineState) -> NodeResult:
    if not config.ENABLE_YOUTUBE:
        return NodeResult(source="youtube", status=STATUS_DISABLED, detail="ENABLE_YOUTUBE is false")

    seen_ids = set()
    video_ids = []
    for term in _search_terms(state):
        for vid in _cached_video_ids(term):
            if vid in seen_ids:
                continue
            seen_ids.add(vid)
            video_ids.append(vid)

    video_ids = video_ids[:config.YOUTUBE_MAX_VIDEOS]
    if not video_ids:
        return NodeResult(source="youtube", status=STATUS_EMPTY)

    blocks = []
    citations = []
    for vid in video_ids:
        text = _cached_transcript(vid)
        if not text:
            continue  # captions disabled/missing for this particular video -- not an error
        blocks.append(text)
        citations.append(f"https://www.youtube.com/watch?v={vid}")

    if not blocks:
        return NodeResult(source="youtube", status=STATUS_EMPTY)

    return NodeResult(source="youtube", status=STATUS_OK, text="\n\n".join(blocks), citations=tuple(citations))
