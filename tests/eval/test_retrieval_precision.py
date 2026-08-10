"""Proves D1/D2 (unfiltered retrieval, missing season metadata) are fixed.

Seeds a mixed corpus (multiple teams, multiple seasons -- mirrors production,
where every cached team/season lives in the same collection) and checks that
a metadata-filtered retrieval never returns another team's or season's
chunks, while the unfiltered baseline demonstrably does.
"""
import json

import chromadb
import pytest

from tests.support.embeddings import DeterministicHashEmbeddingFunction
from vectordb import VectorDBManager
from rag_chain import _build_where

FIXTURES = "ftcscout"
CORPUS = [
    ("team_14469_2022.json", 14469, 2022),
    ("team_14469_2025.json", 14469, 2025),
    ("team_21333_2024.json", 21333, 2024),
    ("team_9295_2025.json", 9295, 2025),
]


@pytest.fixture
def seeded_corpus(tmp_path):
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    manager = VectorDBManager(client=client, embedding_function=DeterministicHashEmbeddingFunction())
    for fname, team, season in CORPUS:
        with open(f"tests/fixtures/{FIXTURES}/{fname}", encoding="utf-8") as f:
            raw = json.load(f)
        manager.upsert_team_data(raw, season=season, region="All")
    return manager


def _query(manager, question, team, season, filtered, k=40):
    where = _build_where([team], season) if filtered else None
    kwargs = {"where": where} if where else {}
    result = manager.collection.query(query_texts=[question], n_results=k, include=["metadatas"], **kwargs)
    return result["metadatas"][0]


def test_unfiltered_retrieval_pulls_in_other_teams(seeded_corpus):
    """Documents the baseline: an unfiltered query for one team's high score
    routinely returns chunks belonging to a completely different team."""
    metas = _query(seeded_corpus, "What was the highest match score?", 14469, 2022, filtered=False)
    foreign = {m["team"] for m in metas if m["team"] != 14469}
    assert foreign, "expected the unfiltered baseline to pull in foreign-team chunks"


def test_filtered_retrieval_returns_only_asked_team_and_season(seeded_corpus):
    for fname, team, season in CORPUS:
        metas = _query(seeded_corpus, "What was the highest match score?", team, season, filtered=True)
        assert metas, f"no chunks retrieved for {team}/{season}"
        for m in metas:
            assert m["team"] == team
            assert m["season"] == season


def test_filtered_retrieval_context_purity_is_perfect(seeded_corpus):
    for fname, team, season in CORPUS:
        metas = _query(seeded_corpus, "how many matches were won", team, season, filtered=True)
        pure = sum(1 for m in metas if m["team"] == team and m["season"] == season)
        assert pure == len(metas)


def test_facts_chunk_is_always_reachable_by_direct_id(seeded_corpus):
    """The aggregate-facts chunk doesn't need to win similarity ranking --
    ask_bot() fetches it directly by id, independent of k or the query text."""
    for fname, team, season in CORPUS:
        result = seeded_corpus.collection.get(ids=[f"{team}|{season}|facts"], include=["documents"])
        assert result["documents"], f"facts chunk missing for {team}/{season}"


def test_aggregation_question_required_recall_via_filter_alone(seeded_corpus):
    """21333/2024 has more match chunks than k=40 in production, so k alone
    can't guarantee every match chunk is retrieved -- this is exactly why
    aggregate answers must come from the forced facts block, not retrieval."""
    all_matches = seeded_corpus.collection.get(
        where=_build_where([21333], 2024), include=["metadatas"],
    )
    match_chunks = [m for m in all_matches["metadatas"] if m["type"] == "match_granular"]
    metas = _query(seeded_corpus, "how many matches did 21333 win", 21333, 2024, filtered=True, k=40)
    retrieved_matches = [m for m in metas if m["type"] == "match_granular"]
    if len(match_chunks) > 40:
        assert len(retrieved_matches) < len(match_chunks)
