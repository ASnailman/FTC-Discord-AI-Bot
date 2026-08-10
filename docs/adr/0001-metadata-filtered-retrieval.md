# ADR 0001: Metadata-filtered retrieval, not global similarity search

## Status

Accepted.

## Context

`/ask` already knows exactly which team number(s) and season a question is about by the time it retrieves context -- `extraction.extract_info` runs before retrieval, and the season is either an explicit slash-command argument or a known default. Despite that, the original retriever (`vector_store.as_retriever(search_kwargs={"k": 40})`) ran a plain top-40 cosine search across the *entire* ChromaDB collection: every team and season ever cached in that process's lifetime, with no filter.

Measured on a realistic mixed corpus, this meant only ~26% of retrieved context actually belonged to the asked team *and* season (`context_purity@40 = 0.257`); the rest was semantically-similar noise from other teams, since scouting text ("Match Q-7 details... Total Points: N") looks similar across completely unrelated teams.

A second, coupled problem made a naive fix worse than doing nothing: chunk metadata didn't reliably carry `season` (only award chunks did, on ~6% of the original store's rows), and chunk ids were a plain positional index (`team_{n}_chunk_{i}`) with no season component at all, so re-fetching a team for a different season could silently overwrite and strand chunks from the first season.

## Decision

Two changes, landed in this order because the second depends on the first:

1. **Chunk schema v2** (`processor.py`, `vectordb.py`): every chunk gets complete metadata (`team`, `season`, `region`, `type`, `schema_version`) and a content-addressed id (`{team}|{season}|<type>|...`) instead of a positional index. `VectorDBManager` upserts by deleting all existing chunks for `(team, season)` before adding the new set, and refuses to operate on a collection stamped with a different `schema_version` (`SchemaMismatchError`) rather than silently mixing chunk formats.
2. **Filtered retrieval** (`rag_chain.py`): `ask_bot` builds a Chroma `where` filter from the team number(s) and season and passes it to the retriever, so the search space is exactly the asked-about data, never a global search.

## Consequences

- `context_purity@40` goes from 0.257 to 1.0 on the same corpus; team precision from 0.593 to 1.0; season precision from 0.379 to 1.0. See [../evaluation-results.md](../evaluation-results.md).
- `ask_bot(team_nums=None, season=None)` remains available and reproduces the original unfiltered behavior exactly -- this is used deliberately by `scripts/eval_retrieval.py --mode before` and `scripts/eval_answers.py --mode before` to keep the "before" measurement a genuine baseline rather than a guess, not as a runtime fallback.
- A downstream consequence, addressed separately: filtering alone doesn't guarantee full recall for aggregate questions when a team has more match chunks than `k`. See [ADR 0002](0002-deterministic-facts-over-llm-arithmetic.md).
