"""End-to-end golden Q/A against the real Gemini model and the real vector
store. Ground truth for every case is computed from the recorded fixture
payload by `stats.compute_team_season_facts`, not hand-typed, so it can
never silently drift from what the fixture actually contains.

Ensures the asked team/season is loaded into the vector store first (via
the same `get_or_load_team` path `/ask` uses), so this doubles as an
integration check of the whole fetch -> chunk -> embed -> retrieve ->
generate pipeline.
"""
import json
from pathlib import Path

import pytest
import yaml

from data_retrieval import fetch_team_data
from rag_chain import ask_bot
from vectordb import VectorDBManager

GOLDEN_PATH = Path(__file__).parent.parent / "fixtures" / "golden" / "qa_golden.yaml"

with open(GOLDEN_PATH, encoding="utf-8") as f:
    CASES = [c for c in yaml.safe_load(f) if c.get("expect_type") != "refusal"]


@pytest.fixture(scope="module")
def vectordb():
    return VectorDBManager()


@pytest.mark.live
@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_golden_answer(case, vectordb):
    vectordb.get_or_load_team(
        team_num=case["team"], fetch_function=fetch_team_data,
        season=case["season"], region=case["region"],
    )

    answer = ask_bot(
        case["question"], team_nums=[case["team"]], season=case["season"], region=case["region"],
    )
    lower = answer.lower()

    for required in case.get("must_contain", []):
        assert required.lower() in lower, f"[{case['id']}] expected {required!r} in answer: {answer!r}"
    for forbidden in case.get("must_not_contain", []):
        assert forbidden.lower() not in lower, f"[{case['id']}] found forbidden {forbidden!r} in answer: {answer!r}"

    assert len(answer) < 2000, "answer exceeds Discord's single-message limit"
    assert answer.rstrip().endswith((".", "!", "?", '"', "'")), f"answer looks truncated: {answer!r}"


@pytest.mark.live
def test_refusal_when_no_team_identified():
    answer = ask_bot("What is the weather like today?", team_nums=None, season=None, region="All")
    assert "don't have that data" in answer.lower() or "no specific team" in answer.lower() or "no verified facts" in answer.lower()
