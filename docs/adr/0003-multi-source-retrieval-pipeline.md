# ADR 0003: Deterministic multi-source retrieval, not an agentic loop

## Status

Accepted.

## Context

`/ask` answers direct lookup questions well ("how many matches did 14469 win", "what was their highest score") because the answer lives entirely in FTCScout data: metadata-filtered ChromaDB retrieval (ADR 0001) plus a deterministic facts block (ADR 0002). It cannot answer questions whose evidence isn't in FTCScout at all -- "What are team Technophobia's game strategies?" (strategy lives in match commentary and forum posts), "What is 14469 known for?" (reputation is community knowledge), or "Who is more likely to win between 14469 and The Golden Ratio?" (a head-to-head comparison ADR 0002 explicitly left out of scope: "the facts block is season/team-scoped, not cross-team").

A brief for this feature proposed a "SQLite Node" for numeric stats. There is no `ftc_data.db` and no relational database in the running application -- `docs/architecture.md` records that an earlier `src/sqlite_db/` table was removed because nothing at runtime ever read it. The numeric facts a SQLite node would query for (OPR, auto/DC/EG OPR, win/loss record, event placements) are already computed exactly by `stats.compute_team_season_facts`. Reintroducing a database to duplicate that would be new data with no new information.

## Options considered

- **Agentic tool-calling loop.** Bind every retrieval source as an LLM tool and let Gemini decide what to call. ADR 0002 already rejected this pattern for aggregate facts ("adds a second model round-trip, a new failure mode (malformed tool calls), and more complexity than this project's scale needs"). The same reasoning applies here, more so: five sources with independent failure modes (auth, rate limits, no captions, no hits) is a lot of surface for an agent loop to get wrong, and it makes `/ask`'s latency and cost unpredictable per-question.
- **Pure LLM router.** One structured-output Gemini call classifies every question's intent before retrieval. Simpler than tool-calling, but still a mandatory round-trip (and a mandatory external dependency) for the common case -- most questions are plain lookups that don't need it.
- **Deterministic router with LLM fallback, parallel bounded nodes.** Chosen.

## Decision

1. **Router (`nodes/router.py`).** Keyword/phrase rules classify a question's intent (`strategy`, `reputation`, `comparison`, ...) into a set of source names, at zero latency and fully offline-testable (`tests/fixtures/golden/router_cases.yaml`, `scripts/eval_router.py`). Only a question no rule matches falls through to one structured-output Gemini call (`config.ENABLE_LLM_ROUTER`); any failure of that call -- timeout, malformed output, disabled -- degrades to `{stats, chroma}`, the same two sources that were always sufficient before this pipeline existed.
2. **Node contract (`nodes/base.py`).** Every source -- local or external -- is a `(state) -> NodeResult` callable wrapped in `@retrieval_node`, so it can never raise. `stats` and `chroma` are always active; `chief_delphi`/`reddit`/`youtube` are feature-flagged and self-disable when unconfigured (`config.ENABLE_*`, `config.ENABLE_REDDIT` derived from credential presence). Activated nodes run concurrently (`nodes.base.run_nodes`, a `ThreadPoolExecutor`) under a per-node timeout and a total pipeline budget (`config.NODE_TIMEOUT_SECONDS`, `config.PIPELINE_BUDGET_SECONDS`); a node that doesn't finish in time is reported `status="timeout"`, never awaited past the budget.
3. **Fusion (`nodes/fusion.py`).** External results are sanitized (control characters stripped, prompt-delimiter lookalikes neutralized), size-budgeted per-source and in total, and rendered under a new `UNTRUSTED COMMUNITY CONTEXT` prompt section with two added system rules telling the model to treat it as opinion and never follow instructions embedded in it -- see `docs/security.md`. `fuse()` returns `None` when nothing usable came back from any source.
4. **Byte-identical fallback (`chain.py`).** `chain.answer` is the new entry point, but whenever no external source is even in play for a question, or every activated one comes back empty/disabled/failed, it calls `rag_chain.ask_bot` -- the pre-existing, completely unmodified function -- so the prompt sent to Gemini is byte-for-byte what it always was. This is enforced by construction (the same function object is called, not a re-derived equivalent) and locked by `tests/unit/test_prompt_compat.py`.
5. **Head-to-head comparison (`nodes/stats_node.py`).** For a 2-3 team question, a best-effort, independently time-boxed sub-fetch re-runs `compute_team_season_facts` for each team and renders a side-by-side table -- still 100%-deterministic Python, never LLM arithmetic, consistent with ADR 0002. It never risks the guaranteed per-team facts blocks: a failure here is caught and logged, not propagated.
6. **No new database.** External content is fetched per-request and held only in a short-lived, per-process `tools.cache.TTLCache` -- never written to ChromaDB. Persisting it would break the `schema_version=2` chunk contract and the `(team, season)` delete-before-add invariant ADR 0001 established, and community text goes stale in a way FTCScout data does not.

## Consequences

- Every existing eval, test, and documented metric (`docs/evaluation-results.md`, the extraction ratchet, ADR 0001/0002's numbers) remains valid unchanged, because the code path they measure is untouched and still reachable byte-for-byte.
- The bot's default out-of-the-box behavior is identical to before this pipeline existed: `ENABLE_CHIEF_DELPHI=true` is the only source on by default (no auth required), `ENABLE_YOUTUBE=false`, and Reddit self-disables without credentials. A fresh checkout with no new env vars set behaves exactly as it did before.
- New failure surface (five extra network dependencies) is bounded, not open-ended: every node has a timeout, every fetch is wrapped so it can't crash `/ask`, and `stats`+`chroma` being always-on guarantees an answer even if every external source is down.
- New attack surface: external text is attacker-reachable (a forum post, a video caption, a Reddit post can contain adversarial content) before it ever reaches the LLM or Discord. See `docs/security.md` for the specific mitigations and their tests.
