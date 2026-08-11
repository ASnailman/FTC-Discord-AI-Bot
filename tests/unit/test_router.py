import yaml
import pytest

import config
from nodes.base import PipelineState
from nodes.router import RouteDecision, route

GOLDEN_PATH = "tests/fixtures/golden/router_cases.yaml"


def _load_cases():
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


CASES = _load_cases()


@pytest.fixture(autouse=True)
def _disable_llm_router(monkeypatch):
    """The golden set below is decided entirely by rules (or the
    `{stats, chroma}` fallback for no-rule-match cases) -- disabling the LLM
    path keeps this whole test module network-free and deterministic."""
    monkeypatch.setattr(config, "ENABLE_LLM_ROUTER", False)


def _state(question: str) -> PipelineState:
    return PipelineState(question=question, team_nums=(14469,), season=2022, region="All")


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_router_case(case):
    decision = route(_state(case["question"]))
    assert decision.sources == frozenset(case["expect_sources"]), (
        f"[{case['id']}] expected {sorted(case['expect_sources'])}, got {sorted(decision.sources)}"
    )


def test_stats_and_chroma_always_present():
    for case in CASES:
        decision = route(_state(case["question"]))
        assert {"stats", "chroma"} <= decision.sources


def test_no_rule_match_uses_fallback_method():
    decision = route(_state("What awards has 14469 won?"))
    assert decision.method == "fallback"
    assert decision.sources == frozenset({"stats", "chroma"})


def test_rule_match_uses_rules_method():
    decision = route(_state("What drivetrain does Technophobia use?"))
    assert decision.method == "rules"
    assert "strategy" in decision.intents


def test_llm_router_disabled_never_calls_llm(monkeypatch):
    """With ENABLE_LLM_ROUTER off, a no-rule-match question must resolve
    without ever importing/calling clients.get_llm."""
    import clients

    def _boom():
        raise AssertionError("router should not have called get_llm with ENABLE_LLM_ROUTER=False")

    monkeypatch.setattr(clients, "get_llm", _boom)
    decision = route(_state("What is the meaning of life?"))
    assert decision.method == "fallback"


def test_llm_router_failure_falls_back_gracefully(monkeypatch):
    """Any exception from the LLM path (bad key, malformed output, timeout)
    must degrade to {stats, chroma}, never raise out of route()."""
    monkeypatch.setattr(config, "ENABLE_LLM_ROUTER", True)

    import clients

    def _broken_llm():
        raise RuntimeError("simulated Gemini failure")

    monkeypatch.setattr(clients, "get_llm", _broken_llm)

    decision = route(_state("What is the meaning of life?"))
    assert decision.method == "fallback"
    assert decision.sources == frozenset({"stats", "chroma"})


def test_route_decision_is_frozen_and_hashable():
    decision = RouteDecision(intents=frozenset({"strategy"}), sources=frozenset({"stats", "chroma"}), method="rules")
    hash(decision)  # must not raise
