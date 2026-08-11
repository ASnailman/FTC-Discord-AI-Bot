"""Chief Delphi (Discourse) search client.

Uses the public search JSON endpoint -- no auth required. Verified live
during planning: `GET /search/query.json?term=<term>` returns
`{"posts": [...], "topics": [...], ...}`; posts carry `topic_id` and
`post_number`, topics carry `id`/`slug`/`title`. This module joins the two
into a flat result list with a constructable permalink.

`SEARCH_URL` is a fixed constant and `term` is always passed via `params=`
(never string-interpolated into the URL), so the only variable part of the
request is safely encoded and the request host can never be redirected by
user input.
"""
import config
from tools import http

SEARCH_URL = "https://www.chiefdelphi.com/search/query.json"


def _permalink(topic: dict, post_number: int) -> str:
    slug = topic.get("slug") or "topic"
    return f"https://www.chiefdelphi.com/t/{slug}/{topic['id']}/{post_number}"


def search(term: str, *, limit: int = 5, timeout: float = None) -> list[dict]:
    """Returns `[{title, blurb, url, username, created_at}]`, truncated to
    `limit`. Chief Delphi is FRC-leaning, so an empty list is the common,
    expected result for most FTC teams -- callers should treat that as a
    normal outcome, not a failure.

    Can raise (`requests` errors, malformed JSON) -- this is a pure I/O
    adapter; `nodes.chief_delphi_node` is what converts failures into a
    `NodeResult(status="error")` instead of propagating.
    """
    timeout = timeout if timeout is not None else max(1.0, config.NODE_TIMEOUT_SECONDS - 1)
    response = http.get(SEARCH_URL, params={"term": term}, timeout=timeout)
    response.raise_for_status()
    data = response.json()

    posts = data.get("posts") or []
    topics_by_id = {t["id"]: t for t in (data.get("topics") or [])}

    results = []
    for post in posts:
        topic = topics_by_id.get(post.get("topic_id"))
        if topic is None:
            continue
        results.append({
            "title": topic.get("fancy_title") or topic.get("title") or "",
            "blurb": post.get("blurb") or "",
            "url": _permalink(topic, post.get("post_number") or 1),
            "username": post.get("username") or "",
            "created_at": post.get("created_at"),
        })
        if len(results) >= limit:
            break
    return results
