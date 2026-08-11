"""Reddit (r/FTC) search client via PRAW, read-only.

No username/password needed -- `client_id` + `client_secret` + `user_agent`
alone puts PRAW in Reddit's "application-only" (client credentials) flow,
which is read-only by default and exactly what a search-only node needs.
"""
from functools import lru_cache

import praw

import config

SUBREDDIT = "FTC"


@lru_cache(maxsize=1)
def get_client() -> "praw.Reddit":
    return praw.Reddit(
        client_id=config.REDDIT_CLIENT_ID,
        client_secret=config.REDDIT_CLIENT_SECRET,
        user_agent=config.REDDIT_USER_AGENT,
        check_for_async=False,
    )


def search_ftc(query: str, *, limit: int = 5, client=None) -> list[dict]:
    """Returns `[{title, selftext_excerpt, url, score, num_comments,
    created_utc}]`, ranked by Reddit's relevance sort over the past year.

    `client` is injectable so tests never need to touch real PRAW/prawcore
    internals -- the same dependency-injection style as
    `vectordb.get_or_load_team`'s `fetch_function` parameter.

    Can raise (prawcore auth/network errors) -- this is a pure I/O adapter;
    `nodes.reddit_node` converts failures into `NodeResult(status="error")`
    instead of propagating.
    """
    client = client or get_client()
    subreddit = client.subreddit(SUBREDDIT)
    results = []
    for submission in subreddit.search(query, sort="relevance", time_filter="year", limit=limit):
        results.append({
            "title": submission.title,
            "selftext_excerpt": (submission.selftext or "")[:500],
            "url": f"https://reddit.com{submission.permalink}",
            "score": submission.score,
            "num_comments": submission.num_comments,
            "created_utc": submission.created_utc,
        })
    return results
