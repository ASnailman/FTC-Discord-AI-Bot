"""Regression lock: the multi-source pipeline must never change the prompt
sent to Gemini when there's no external context to add. This is the
non-negotiable invariant from docs/adr/0003 -- it's what keeps
docs/evaluation-results.md, the live tier, and the extraction ratchet valid
after this pipeline lands.

Two things are locked, by construction rather than by re-deriving the
prompt text:
1. `chain.answer` calls `rag_chain.ask_bot` -- the literal, unmodified
   function -- whenever no external node is active or all activated
   external nodes come back empty/disabled/failed. Because it's the same
   function object, the resulting prompt is trivially byte-identical.
2. When external context *is* fused in, the extended prompt is provably an
   *extension* of the original: `chain.EXTENDED_SYSTEM_PROMPT` starts with
   `rag_chain.SYSTEM_PROMPT` verbatim, so rules 1-6 and the VERIFIED
   FACTS/CONTEXT slots are never altered, only appended to.
"""
from unittest.mock import Mock

import pytest

import chain
import config
import rag_chain


@pytest.fixture(autouse=True)
def _disable_llm_router(monkeypatch):
    """These tests exercise chain.answer's fallback logic, not routing
    itself (see tests/unit/test_router.py for that) -- disabling the LLM
    path keeps this module fast, deterministic, and (defense in depth on
    top of conftest._block_network) unable to make a real Gemini call."""
    monkeypatch.setattr(config, "ENABLE_LLM_ROUTER", False)


# --- (1) no-external-sources delegates to the unmodified ask_bot ---

def test_no_active_external_sources_delegates_to_ask_bot_unchanged(monkeypatch):
    monkeypatch.setattr(chain, "EXTERNAL_NODES", {})
    mock_ask_bot = Mock(return_value="the exact original answer")
    monkeypatch.setattr(rag_chain, "ask_bot", mock_ask_bot)

    result = chain.answer("How many matches did 14469 win?", team_nums=[14469], season=2022, region="All")

    assert result == "the exact original answer"
    mock_ask_bot.assert_called_once_with(
        "How many matches did 14469 win?", team_nums=(14469,), season=2022, region="All", k=None,
    )


def test_explicit_empty_sources_delegates_to_ask_bot_unchanged(monkeypatch):
    mock_ask_bot = Mock(return_value="stub")
    monkeypatch.setattr(rag_chain, "ask_bot", mock_ask_bot)

    chain.answer("What was the highest score?", team_nums=[14469], season=2022, region="All", sources=())

    mock_ask_bot.assert_called_once()


def test_no_team_nums_still_delegates_and_passes_none_through(monkeypatch):
    monkeypatch.setattr(chain, "EXTERNAL_NODES", {})
    mock_ask_bot = Mock(return_value="refusal message")
    monkeypatch.setattr(rag_chain, "ask_bot", mock_ask_bot)

    chain.answer("What is the meaning of life?", team_nums=None, season=None, region=None)

    mock_ask_bot.assert_called_once_with(
        "What is the meaning of life?", team_nums=None, season=None, region=None, k=None,
    )


def test_all_external_nodes_empty_falls_back_to_ask_bot_unchanged(monkeypatch):
    """Even when a source *is* activated, if it produces nothing usable the
    call still collapses to the unmodified ask_bot path -- fuse() returning
    None is exactly the signal for this."""
    from nodes.base import NodeResult

    def empty_node(state):
        return NodeResult(source="chief_delphi", status="empty")

    monkeypatch.setattr(chain, "EXTERNAL_NODES", {"chief_delphi": empty_node})
    mock_ask_bot = Mock(return_value="fallback answer")
    monkeypatch.setattr(rag_chain, "ask_bot", mock_ask_bot)

    result = chain.answer(
        "What's team 14469's strategy?", team_nums=[14469], season=2022, region="All",
        sources=("chief_delphi",),
    )

    assert result == "fallback answer"
    mock_ask_bot.assert_called_once()


def test_two_teams_no_external_content_but_real_head_to_head_does_not_fall_back(monkeypatch):
    """A comparison question with 2+ teams and zero external sources active
    must still get the richer prompt if `stats_node` actually produced a
    head-to-head table -- this is the case chain.answer's `sources=None`
    path exists for (see nodes/stats_node.py:render_head_to_head)."""
    from nodes.base import NodeResult
    from nodes.stats_node import HEAD_TO_HEAD_MARKER

    monkeypatch.setattr(chain, "EXTERNAL_NODES", {})
    mock_ask_bot = Mock(return_value="should not be called")
    monkeypatch.setattr(rag_chain, "ask_bot", mock_ask_bot)

    def fake_stats_node(state):
        return NodeResult(
            source="stats", status="ok",
            text=f"Team 14469 facts.\n\nTeam 9295 facts.\n\n{HEAD_TO_HEAD_MARKER}: Team 14469 edges Team 9295.",
        )

    def fake_chroma_node(state):
        return NodeResult(source="chroma", status="ok", text="Match context.")

    monkeypatch.setattr(chain, "stats_node", fake_stats_node)
    monkeypatch.setattr(chain, "chroma_node", fake_chroma_node)

    captured = {}

    class FakeResponse:
        content = "Team 14469 is more likely to win."

    class FakeLLM:
        def invoke(self, messages):
            captured["messages"] = messages
            return FakeResponse()

    monkeypatch.setattr(chain, "get_llm_with_context", lambda: FakeLLM())

    result = chain.answer(
        "Who is more likely to win between 14469 and 9295?",
        team_nums=[14469, 9295], season=2025, region="All",
    )

    mock_ask_bot.assert_not_called()
    assert HEAD_TO_HEAD_MARKER in str(captured["messages"])
    assert "Team 14469 is more likely to win." in result


def test_two_teams_head_to_head_fetch_failed_falls_back_to_ask_bot_unchanged(monkeypatch):
    """The mirror case: 2+ teams, but stats_node's best-effort head-to-head
    didn't produce a table (e.g. an FTCScout fetch failed) AND no external
    source has content either -- must still collapse to the byte-identical
    fallback rather than sending a needlessly-larger prompt with nothing
    new in it."""
    monkeypatch.setattr(chain, "EXTERNAL_NODES", {})
    mock_ask_bot = Mock(return_value="unchanged answer")
    monkeypatch.setattr(rag_chain, "ask_bot", mock_ask_bot)

    from nodes.base import NodeResult

    def fake_stats_node(state):
        # No head-to-head marker -- the enrichment attempt didn't pan out.
        return NodeResult(source="stats", status="ok", text="Team 14469 facts.\n\nTeam 9295 facts.")

    def fake_chroma_node(state):
        return NodeResult(source="chroma", status="ok", text="Match context.")

    monkeypatch.setattr(chain, "stats_node", fake_stats_node)
    monkeypatch.setattr(chain, "chroma_node", fake_chroma_node)

    result = chain.answer(
        "Who is more likely to win between 14469 and 9295?",
        team_nums=[14469, 9295], season=2025, region="All",
    )

    assert result == "unchanged answer"
    mock_ask_bot.assert_called_once()


# --- (2) the extended prompt is provably an extension, not a modification ---

def test_extended_system_prompt_starts_with_original_verbatim():
    assert chain.EXTENDED_SYSTEM_PROMPT.startswith(rag_chain.SYSTEM_PROMPT)


def test_extended_system_prompt_preserves_original_slots():
    assert "VERIFIED FACTS:\n{facts}" in chain.EXTENDED_SYSTEM_PROMPT
    assert "CONTEXT:\n{context}" in chain.EXTENDED_SYSTEM_PROMPT


def test_extended_system_prompt_adds_a_clearly_separate_untrusted_section():
    assert "UNTRUSTED COMMUNITY CONTEXT:\n{community_context}" in chain.EXTENDED_SYSTEM_PROMPT
    # The untrusted section must come after, not interleaved with, the
    # original rules/slots.
    original_end = chain.EXTENDED_SYSTEM_PROMPT.index(rag_chain.SYSTEM_PROMPT) + len(rag_chain.SYSTEM_PROMPT)
    untrusted_start = chain.EXTENDED_SYSTEM_PROMPT.index("UNTRUSTED COMMUNITY CONTEXT:")
    assert untrusted_start >= original_end


# --- (3) when external content IS fused, it reaches the LLM via the extended prompt ---

def test_fused_path_calls_llm_with_extended_prompt_and_appends_footer(monkeypatch):
    from nodes.base import NodeResult

    def cd_node(state):
        return NodeResult(
            source="chief_delphi", status="ok",
            text="Team 14469 uses a four-bar linkage intake.",
            citations=("https://www.chiefdelphi.com/t/example/1",),
        )

    monkeypatch.setattr(chain, "EXTERNAL_NODES", {"chief_delphi": cd_node})

    from nodes.base import NodeResult as NR

    def fake_stats_node(state):
        return NR(source="stats", status="ok", text="Team 14469 season OPR: 42.0.")

    def fake_chroma_node(state):
        return NR(source="chroma", status="ok", text="Match Q-7 details...")

    monkeypatch.setattr(chain, "stats_node", fake_stats_node)
    monkeypatch.setattr(chain, "chroma_node", fake_chroma_node)

    captured = {}

    class FakeResponse:
        content = "Team 14469 likely wins based on OPR."

    class FakeLLM:
        def invoke(self, messages):
            captured["messages"] = messages
            return FakeResponse()

    monkeypatch.setattr(chain, "get_llm_with_context", lambda: FakeLLM())

    result = chain.answer(
        "What's team 14469's strategy?", team_nums=[14469], season=2022, region="All",
        sources=("chief_delphi",),
    )

    assert "messages" in captured
    rendered = str(captured["messages"])
    assert "four-bar linkage" in rendered
    assert "Chief Delphi" in rendered
    assert "Team 14469 likely wins based on OPR." in result
    assert "Sources consulted" in result
    assert "Chief Delphi" in result
