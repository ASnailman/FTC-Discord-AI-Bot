# ADR 0002: Deterministic facts block, not LLM arithmetic over retrieved chunks

## Status

Accepted.

## Context

Even with retrieval correctly filtered to the right team and season (ADR 0001), aggregate questions -- "what was the highest match score", "how many matches did they win" -- are structurally different from lookup questions. The correct answer requires an exact max/sum/count over *every* match or event chunk for that team/season, not a similarity-ranked sample of them. Two problems follow directly:

1. Match chunks are near-duplicate text ("Match Q-N details... Total Points: N. Scoring Breakdown: ..."), so which ones rank in the top-k by cosine similarity to a question like "what was the highest score" is close to arbitrary -- semantic similarity doesn't encode numeric ordering.
2. A team can have more match chunks in a season than `k` (a full season is commonly 30-50+ matches across all events; `k` defaults to 40). No filter can guarantee 100% recall of "every match chunk" within a fixed-size top-k retrieval.

## Options considered

- **A larger summary chunk, retrieved like any other.** Simplest change, but it still has to *win* similarity ranking to appear in context at all -- exactly the non-determinism being removed, just moved one level up.
- **Tool-calling / agentic loop** (let the LLM call a "compute stats" function). More flexible, but adds a second model round-trip, a new failure mode (malformed tool calls), and more complexity than this project's scale needs, for a set of aggregates that are cheap to compute unconditionally.
- **Precompute in Python, force-include by direct id lookup.** Chosen.

## Decision

`stats.compute_team_season_facts(data, season, region)` computes the aggregates (highest/lowest match score with event+match attribution, win/loss/tie record, mean/median, season OPR, award count and list, per-event records) directly from the raw payload in Python -- 100% recall by construction, no ranking involved. `render_facts_block` renders it to text, which is stored as a normal retrievable `season_facts` chunk (so it's inspectable and consistent with everything else in the store) **and** fetched directly by its content-addressed id (`vector_store.get(ids=[f"{team}|{season}|facts"])`) before the retrieval chain runs, so its presence in the prompt never depends on `k` or similarity ranking.

The system prompt marks this block authoritative and instructs the model not to recompute or contradict it: *"The VERIFIED FACTS block is authoritative and already computed... do not add, average, or compare numbers yourself."*

## Consequences

- Aggregate answers are now exactly correct by construction rather than probabilistically likely to be correct. Measured: `required_facts_present_rate` (the retrieved/generated answer contains the exact expected fact) goes from 0.143 to 1.0 on the live golden set -- see [../evaluation-results.md](../evaluation-results.md).
- One extra Chroma `get(ids=...)` call per `/ask`, negligible relative to the embedding/LLM cost already in the request.
- The facts block is season/team-scoped, not cross-team -- a question comparing two teams still relies on retrieval + the LLM to combine two separate facts blocks (both are force-included when multiple teams are identified), not a single precomputed comparison.
