import config
from tools import reddit


class _FakeSubmission:
    def __init__(self, title, selftext, permalink, score, num_comments, created_utc):
        self.title = title
        self.selftext = selftext
        self.permalink = permalink
        self.score = score
        self.num_comments = num_comments
        self.created_utc = created_utc


class _FakeSubreddit:
    def __init__(self, submissions):
        self._submissions = submissions
        self.last_call = None

    def search(self, query, sort=None, time_filter=None, limit=None):
        self.last_call = {"query": query, "sort": sort, "time_filter": time_filter, "limit": limit}
        subset = self._submissions[:limit] if limit is not None else self._submissions
        return iter(subset)


class _FakeRedditClient:
    def __init__(self, submissions):
        self.subreddit_instance = _FakeSubreddit(submissions)

    def subreddit(self, name):
        assert name == reddit.SUBREDDIT
        return self.subreddit_instance


SAMPLE_SUBMISSIONS = [
    _FakeSubmission(
        title="14469 HOW Robot Reveal 2025", selftext="Check out our robot for this season!",
        permalink="/r/FTC/comments/abc123/14469_reveal/", score=42, num_comments=7, created_utc=1700000000.0,
    ),
    _FakeSubmission(
        title="Team 9295 build thread", selftext="", permalink="/r/FTC/comments/def456/9295_build/",
        score=10, num_comments=2, created_utc=1700000100.0,
    ),
]


def test_search_ftc_returns_expected_shape():
    client = _FakeRedditClient(SAMPLE_SUBMISSIONS)
    results = reddit.search_ftc("14469", client=client)

    assert len(results) == 2
    assert results[0]["title"] == "14469 HOW Robot Reveal 2025"
    assert results[0]["url"] == "https://reddit.com/r/FTC/comments/abc123/14469_reveal/"
    assert results[0]["score"] == 42
    assert results[0]["num_comments"] == 7


def test_search_ftc_handles_empty_selftext():
    client = _FakeRedditClient(SAMPLE_SUBMISSIONS)
    results = reddit.search_ftc("9295", client=client)
    assert results[1]["selftext_excerpt"] == ""


def test_search_ftc_truncates_long_selftext():
    long_post = _FakeSubmission(
        title="long", selftext="x" * 1000, permalink="/r/FTC/comments/x/y/",
        score=1, num_comments=0, created_utc=0,
    )
    client = _FakeRedditClient([long_post])
    results = reddit.search_ftc("x", client=client)
    assert len(results[0]["selftext_excerpt"]) == 500


def test_search_ftc_respects_limit():
    client = _FakeRedditClient(SAMPLE_SUBMISSIONS)
    reddit.search_ftc("x", limit=1, client=client)
    assert client.subreddit_instance.last_call["limit"] == 1


def test_search_ftc_uses_relevance_sort_and_year_filter():
    client = _FakeRedditClient(SAMPLE_SUBMISSIONS)
    reddit.search_ftc("x", client=client)
    call = client.subreddit_instance.last_call
    assert call["sort"] == "relevance"
    assert call["time_filter"] == "year"


def test_search_ftc_no_results():
    client = _FakeRedditClient([])
    assert reddit.search_ftc("nonexistent team", client=client) == []


def test_get_client_reads_config(monkeypatch):
    """get_client() must be constructed from config, not hardcoded creds --
    exercised via a patched praw.Reddit constructor so no real client/auth
    object is ever built."""
    captured = {}

    class _FakePrawReddit:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(config, "REDDIT_CLIENT_ID", "test-id")
    monkeypatch.setattr(config, "REDDIT_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(config, "REDDIT_USER_AGENT", "test-agent")
    monkeypatch.setattr(reddit, "praw", type("praw_stub", (), {"Reddit": _FakePrawReddit}))
    reddit.get_client.cache_clear()

    reddit.get_client()

    assert captured["client_id"] == "test-id"
    assert captured["client_secret"] == "test-secret"
    assert captured["user_agent"] == "test-agent"
    reddit.get_client.cache_clear()
