"""Chief Delphi Node: community forum search, activated by the router for
strategy/reputation questions (see nodes/router.py). No auth required --
enabled by default (`config.ENABLE_CHIEF_DELPHI`).
"""
import config
from nodes.base import NodeResult, PipelineState, STATUS_DISABLED, STATUS_EMPTY, STATUS_OK, retrieval_node
from tools import discourse
from tools.cache import TTLCache

_cache = TTLCache(ttl_seconds=config.EXTERNAL_CACHE_TTL_MINUTES * 60)


def _search_terms(state: PipelineState) -> list[str]:
    terms = [f"{t} FTC" for t in state.team_nums]
    terms.extend(f"{name} FTC" for name in state.team_names)
    return terms or [f"{state.question} FTC"]


def _cached_search(term: str) -> list[dict]:
    cache_key = f"chief_delphi:{term}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached
    results = discourse.search(term, limit=config.CHIEF_DELPHI_MAX_POSTS)
    _cache.set(cache_key, results)
    return results


@retrieval_node("chief_delphi")
def chief_delphi_node(state: PipelineState) -> NodeResult:
    if not config.ENABLE_CHIEF_DELPHI:
        return NodeResult(source="chief_delphi", status=STATUS_DISABLED, detail="ENABLE_CHIEF_DELPHI is false")

    seen_urls = set()
    posts = []
    for term in _search_terms(state):
        for post in _cached_search(term):
            if post["url"] in seen_urls:
                continue
            seen_urls.add(post["url"])
            posts.append(post)

    posts = posts[:config.CHIEF_DELPHI_MAX_POSTS]
    if not posts:
        return NodeResult(source="chief_delphi", status=STATUS_EMPTY)

    lines = [f"\"{p['title']}\" by {p['username']}: {p['blurb']}" for p in posts]
    citations = tuple(p["url"] for p in posts)
    return NodeResult(source="chief_delphi", status=STATUS_OK, text="\n\n".join(lines), citations=citations)
