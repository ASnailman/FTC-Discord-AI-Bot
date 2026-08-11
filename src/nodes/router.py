"""Deterministic-first query router.

Rules run first and cost nothing offline-testable and zero-latency; a
structured-output Gemini call only fires when no rule matches AND
`config.ENABLE_LLM_ROUTER` is set. Any failure of that call (timeout,
malformed output, disabled) falls back to `{stats, chroma}` -- the same
sources that already guarantee the pipeline can always answer.

This is deliberately NOT an agentic tool-calling loop: ADR 0002 already
rejected that pattern (a second model round-trip, a new malformed-tool-call
failure mode) for a project at this scale, and that reasoning applies here
too -- see docs/adr/0003.
"""
from dataclasses import dataclass

import config
from logging_setup import get_logger
from nodes.base import PipelineState

logger = get_logger(__name__)

LOCAL_SOURCES = frozenset({"stats", "chroma"})
ALL_EXTERNAL_SOURCES = frozenset({"chief_delphi", "reddit", "youtube"})

# Substring phrases, matched against `f" {question.lower()} "` so a phrase
# at the very start/end of the question still matches with its boundary
# spaces intact.
INTENT_RULES: dict[str, frozenset] = {
    "strategy": frozenset({
        "strategy", "strategies", "drivetrain", "intake", "auto path", "autonomous path",
        "cycle time", "cycling", "reveal", "how do they play", "how they play",
        "play style", "playstyle", "how does their robot", "how do their robots",
    }),
    "reputation": frozenset({
        "known for", "reputation", "notable", "respected", "well known",
        "what do people say", "community think", "well regarded",
    }),
    "comparison": frozenset({
        " vs ", " vs. ", "versus", "beat ", "beating", "better than", "more likely",
        "who would win", "who is more likely", "matchup", "alliance partner",
        "which team is better", "compare ", "head to head", "head-to-head",
    }),
}

INTENT_SOURCES: dict[str, frozenset] = {
    "strategy": frozenset({"youtube", "chief_delphi"}),
    "reputation": frozenset({"chief_delphi", "reddit"}),
    "comparison": frozenset({"reddit"}),
}


@dataclass(frozen=True)
class RouteDecision:
    intents: frozenset
    sources: frozenset
    method: str  # "rules" | "llm" | "fallback"


def _match_rules(question: str) -> frozenset:
    q = f" {question.lower()} "
    intents = set()
    for intent, phrases in INTENT_RULES.items():
        if any(phrase in q for phrase in phrases):
            intents.add(intent)
    return frozenset(intents)


def _sources_for(intents: frozenset) -> frozenset:
    sources = set(LOCAL_SOURCES)
    for intent in intents:
        sources |= INTENT_SOURCES.get(intent, frozenset())
    return frozenset(sources)


def _llm_route(question: str) -> "RouteDecision | None":
    """Structured-output classification for questions no rule matched.
    Returns None on any failure so the caller falls back to {stats, chroma}."""
    if not config.ENABLE_LLM_ROUTER:
        return None
    try:
        from pydantic import BaseModel, Field

        from clients import get_llm  # local import: router stays importable with no LLM configured

        class _LLMRouteDecision(BaseModel):
            intents: list[str] = Field(
                description=(
                    "Which apply to the question: strategy (robot design/gameplay "
                    "strategy), reputation (community opinion/notability), comparison "
                    "(head-to-head or hypothetical matchup), stats_lookup (a direct "
                    "numeric fact). Empty list if none apply."
                )
            )

        structured_llm = get_llm().with_structured_output(_LLMRouteDecision)
        decision = structured_llm.invoke(
            "Classify this FTC (FIRST Tech Challenge) scouting question by intent.\n"
            f"Question: {question}"
        )
        intents = frozenset(i for i in decision.intents if i in INTENT_SOURCES)
        return RouteDecision(intents=intents, sources=_sources_for(intents), method="llm")
    except Exception:  # noqa: BLE001 -- a routing failure must never block /ask
        logger.exception("LLM router failed; falling back to {stats, chroma}")
        return None


def route(state: PipelineState) -> RouteDecision:
    intents = _match_rules(state.question)
    if intents:
        return RouteDecision(intents=intents, sources=_sources_for(intents), method="rules")

    llm_decision = _llm_route(state.question)
    if llm_decision is not None:
        return llm_decision

    return RouteDecision(intents=frozenset(), sources=frozenset(LOCAL_SOURCES), method="fallback")
