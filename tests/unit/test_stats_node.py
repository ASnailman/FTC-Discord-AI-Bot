from stats import compute_team_season_facts
from nodes.base import PipelineState
from nodes.stats_node import (
    HEAD_TO_HEAD_MARKER,
    _fetch_facts_dicts_bounded,
    render_head_to_head,
    stats_node,
)
from textutils import fmt


# --- render_head_to_head: pure function, ground truth from compute_team_season_facts ---

def test_render_head_to_head_needs_at_least_two_teams(payload_9295_2025):
    facts = compute_team_season_facts(payload_9295_2025, 2025, "All")
    assert render_head_to_head([facts]) == ""
    assert render_head_to_head([]) == ""
    assert render_head_to_head([None, None]) == ""


def test_render_head_to_head_drops_none_entries(payload_9295_2025):
    facts = compute_team_season_facts(payload_9295_2025, 2025, "All")
    # Only one real dict survives after dropping the failed fetch -> "".
    assert render_head_to_head([facts, None]) == ""


def test_render_head_to_head_two_teams_uses_real_ground_truth_numbers(payload_9295_2025, payload_9930_2025_sparse):
    facts_a = compute_team_season_facts(payload_9295_2025, 2025, "All")
    facts_b = compute_team_season_facts(payload_9930_2025_sparse, 2025, "All")

    table = render_head_to_head([facts_a, facts_b])

    assert table.startswith(HEAD_TO_HEAD_MARKER)
    assert f"Team {facts_a['team']}" in table
    assert f"Team {facts_b['team']}" in table
    # Every non-None numeric value that went into the table is the exact
    # value compute_team_season_facts produced -- never hand-typed.
    if facts_a["season_opr"] is not None:
        assert fmt(facts_a["season_opr"]) in table
    if facts_b["season_opr"] is not None:
        assert fmt(facts_b["season_opr"]) in table
    assert f"{facts_a['wins']}-{facts_a['losses']}-{facts_a['ties']}" in table
    assert f"{facts_b['wins']}-{facts_b['losses']}-{facts_b['ties']}" in table


def test_render_head_to_head_picks_correct_edge_direction():
    facts_high = {
        "team": 1, "name": "High", "season_opr": 50.0, "auto_opr": None, "dc_opr": None,
        "eg_opr": None, "mean_points": None, "wins": 5, "losses": 1, "ties": 0, "award_count": 0,
    }
    facts_low = {
        "team": 2, "name": "Low", "season_opr": 20.0, "auto_opr": None, "dc_opr": None,
        "eg_opr": None, "mean_points": None, "wins": 1, "losses": 5, "ties": 0, "award_count": 0,
    }
    table = render_head_to_head([facts_high, facts_low])
    assert "Season OPR" in table
    opr_line = next(line for line in table.splitlines() if "Season OPR" in line)
    assert "edge: Team 1" in opr_line


def test_render_head_to_head_skips_axis_when_both_sides_missing():
    facts_a = {
        "team": 1, "name": "A", "season_opr": None, "auto_opr": None, "dc_opr": None,
        "eg_opr": None, "mean_points": None, "wins": 0, "losses": 0, "ties": 0, "award_count": 0,
    }
    facts_b = dict(facts_a, team=2, name="B")
    table = render_head_to_head([facts_a, facts_b])
    assert "Season OPR" not in table  # both sides None -> axis omitted entirely
    assert "Record (W-L-T)" in table  # record is always shown


# --- _fetch_facts_dicts_bounded: bounded, parallel, tolerant of per-team failure ---

def test_fetch_facts_dicts_bounded_returns_none_for_failed_team(monkeypatch, payload_9295_2025):
    def fake_fetch(team_number, season, region):
        if team_number == 9295:
            return payload_9295_2025
        raise ConnectionError("simulated failure")

    monkeypatch.setattr("nodes.stats_node.data_retrieval.fetch_team_data", fake_fetch)

    results = _fetch_facts_dicts_bounded((9295, 99999), 2025, "All", budget_seconds=2.0)

    assert results[0] is not None
    assert results[0]["team"] == 9295
    assert results[1] is None


def test_fetch_facts_dicts_bounded_preserves_team_order(monkeypatch, payload_9295_2025, payload_9930_2025_sparse):
    fixtures = {9295: payload_9295_2025, 9930: payload_9930_2025_sparse}
    monkeypatch.setattr(
        "nodes.stats_node.data_retrieval.fetch_team_data",
        lambda team_number, season, region: fixtures[team_number],
    )

    results = _fetch_facts_dicts_bounded((9930, 9295), 2025, "All", budget_seconds=2.0)

    assert results[0]["team"] == 9930
    assert results[1]["team"] == 9295


def test_fetch_facts_dicts_bounded_times_out_gracefully(monkeypatch):
    import time

    def slow_fetch(team_number, season, region):
        time.sleep(2)
        return None

    monkeypatch.setattr("nodes.stats_node.data_retrieval.fetch_team_data", slow_fetch)

    start = time.monotonic()
    results = _fetch_facts_dicts_bounded((1, 2), 2025, "All", budget_seconds=0.2)
    elapsed = time.monotonic() - start

    assert results == [None, None]
    assert elapsed < 1.0


# --- stats_node integration: head-to-head is appended, but never at the cost of the base facts ---

class _FakeVectorStore:
    def __init__(self, docs):
        self._docs = docs

    def get(self, ids, include=None):
        return {"documents": self._docs}


def test_stats_node_single_team_has_no_head_to_head(monkeypatch):
    monkeypatch.setattr(
        "nodes.stats_node.get_vector_store", lambda: _FakeVectorStore(["Team 14469 facts here."]),
    )
    state = PipelineState(question="x", team_nums=(14469,), season=2022, region="All")

    result = stats_node(state)

    assert result.status == "ok"
    assert HEAD_TO_HEAD_MARKER not in result.text


def test_stats_node_two_teams_appends_head_to_head(monkeypatch, payload_9295_2025, payload_9930_2025_sparse):
    monkeypatch.setattr(
        "nodes.stats_node.get_vector_store",
        lambda: _FakeVectorStore(["Team 9295 facts.", "Team 9930 facts."]),
    )
    fixtures = {9295: payload_9295_2025, 9930: payload_9930_2025_sparse}
    monkeypatch.setattr(
        "nodes.stats_node.data_retrieval.fetch_team_data",
        lambda team_number, season, region: fixtures[team_number],
    )

    state = PipelineState(question="x", team_nums=(9295, 9930), season=2025, region="All")
    result = stats_node(state)

    assert result.status == "ok"
    assert "Team 9295 facts." in result.text  # base facts_block preserved
    assert "Team 9930 facts." in result.text
    assert HEAD_TO_HEAD_MARKER in result.text


def test_stats_node_head_to_head_failure_still_returns_base_facts(monkeypatch):
    monkeypatch.setattr(
        "nodes.stats_node.get_vector_store",
        lambda: _FakeVectorStore(["Team 9295 facts.", "Team 9930 facts."]),
    )

    def broken_fetch(team_number, season, region):
        raise RuntimeError("FTCScout is down")

    monkeypatch.setattr("nodes.stats_node.data_retrieval.fetch_team_data", broken_fetch)

    state = PipelineState(question="x", team_nums=(9295, 9930), season=2025, region="All")
    result = stats_node(state)  # must not raise, must not lose the base facts

    assert result.status == "ok"
    assert "Team 9295 facts." in result.text
    assert "Team 9930 facts." in result.text
    assert HEAD_TO_HEAD_MARKER not in result.text


def test_stats_node_more_than_max_comparison_teams_skips_head_to_head(monkeypatch):
    monkeypatch.setattr(
        "nodes.stats_node.get_vector_store", lambda: _FakeVectorStore(["facts"] * 4),
    )
    state = PipelineState(question="x", team_nums=(1, 2, 3, 4), season=2025, region="All")

    result = stats_node(state)

    assert HEAD_TO_HEAD_MARKER not in result.text
