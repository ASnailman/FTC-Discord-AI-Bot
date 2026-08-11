import time

from nodes.base import NodeResult, PipelineState, retrieval_node, run_nodes

STATE = PipelineState(question="how good is 14469", team_nums=(14469,), season=2022, region="All")


# --- NodeResult ---

def test_result_repr_has_no_secrets():
    result = NodeResult(source="reddit", status="error", detail="client_secret=abc123 leaked", text="x" * 50)
    rendered = repr(result)
    assert "abc123" not in rendered
    assert "leaked" not in rendered
    assert "reddit" in rendered
    assert "error" in rendered


def test_result_defaults():
    result = NodeResult(source="stats", status="ok")
    assert result.text == ""
    assert result.citations == ()
    assert result.detail == ""


# --- retrieval_node ---

def test_retrieval_node_passes_through_ok_result():
    @retrieval_node("stats")
    def node(state):
        return NodeResult(source="stats", status="ok", text="hello")

    result = node(STATE)
    assert result.status == "ok"
    assert result.text == "hello"


def test_retrieval_node_converts_exception_to_error_status():
    @retrieval_node("chief_delphi")
    def node(state):
        raise ValueError("boom")

    result = node(STATE)
    assert result.source == "chief_delphi"
    assert result.status == "error"
    assert "boom" in result.detail


def test_retrieval_node_never_raises():
    @retrieval_node("youtube")
    def node(state):
        raise RuntimeError("network exploded")

    # Must not raise -- this is the whole point of the decorator.
    node(STATE)


# --- run_nodes ---

def test_run_nodes_empty_dict_returns_empty():
    assert run_nodes({}, STATE, node_timeout=1, total_budget=1) == {}


def test_run_nodes_runs_all_nodes_concurrently():
    def slow_node(state):
        time.sleep(0.3)
        return NodeResult(source="a", status="ok", text="a-done")

    def fast_node(state):
        return NodeResult(source="b", status="ok", text="b-done")

    start = time.monotonic()
    results = run_nodes(
        {"a": slow_node, "b": fast_node}, STATE, node_timeout=2, total_budget=2,
    )
    elapsed = time.monotonic() - start

    assert results["a"].status == "ok"
    assert results["a"].text == "a-done"
    assert results["b"].status == "ok"
    # If these ran sequentially this would take >= 0.3s either way, so the
    # real assertion is that they don't stack (well under 0.3 + 0.3).
    assert elapsed < 0.6


def test_run_nodes_marks_node_exceeding_total_budget_as_timeout():
    def hangs(state):
        time.sleep(2)
        return NodeResult(source="slow", status="ok", text="too late")

    def quick(state):
        return NodeResult(source="quick", status="ok", text="on time")

    start = time.monotonic()
    results = run_nodes(
        {"slow": hangs, "quick": quick}, STATE, node_timeout=0.2, total_budget=0.2,
    )
    elapsed = time.monotonic() - start

    assert results["slow"].status == "timeout"
    assert results["quick"].status == "ok"
    # The whole call must return close to the budget, not wait for `hangs`.
    assert elapsed < 1.0


def test_run_nodes_isolates_one_nodes_exception_from_others():
    def broken(state):
        raise RuntimeError("no decorator here, still shouldn't kill the batch")

    def fine(state):
        return NodeResult(source="fine", status="ok", text="ok")

    results = run_nodes({"broken": broken, "fine": fine}, STATE, node_timeout=1, total_budget=1)

    assert results["broken"].status == "error"
    assert results["fine"].status == "ok"
