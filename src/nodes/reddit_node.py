"""Reddit Node: r/FTC search, activated by the router for
reputation/comparison questions (see nodes/router.py). Self-disables when
Reddit credentials aren't configured -- `config.ENABLE_REDDIT` is derived
from their presence, not a literal on/off flag.
"""
import config
from nodes.base import NodeResult, PipelineState, STATUS_DISABLED, STATUS_EMPTY, STATUS_OK, retrieval_node
from tools import reddit
from tools.cache import TTLCache

_cache = TTLCache(ttl_seconds=config.EXTERNAL_CACHE_TTL_MINUTES * 60)


def _search_terms(state: PipelineState) -> list[str]:
    terms = [str(t) for t in state.team_nums]
    terms.extend(state.team_names)
    return terms or [state.question]


def _cached_search(term: str) -> list[dict]:
    cache_key = f"reddit:{term}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached
    results = reddit.search_ftc(term, limit=config.REDDIT_MAX_POSTS)
    _cache.set(cache_key, results)
    return results


@retrieval_node("reddit")
def reddit_node(state: PipelineState) -> NodeResult:
    if not config.ENABLE_REDDIT:
        return NodeResult(source="reddit", status=STATUS_DISABLED, detail="ENABLE_REDDIT is false (missing creds)")

    seen_urls = set()
    posts = []
    for term in _search_terms(state):
        for post in _cached_search(term):
            if post["url"] in seen_urls:
                continue
            seen_urls.add(post["url"])
            posts.append(post)

    posts = posts[:config.REDDIT_MAX_POSTS]
    if not posts:
        return NodeResult(source="reddit", status=STATUS_EMPTY)

    lines = [
        f"\"{p['title']}\" ({p['score']} upvotes, {p['num_comments']} comments): {p['selftext_excerpt']}"
        for p in posts
    ]
    citations = tuple(p["url"] for p in posts)
    return NodeResult(source="reddit", status=STATUS_OK, text="\n\n".join(lines), citations=citations)
