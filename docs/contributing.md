# Contributing

## Before pushing

```bash
pytest -m "not live"    # must be green; this is what CI runs on every push
ruff check .
```

Run the live tier locally if you touched `extraction.py`, `rag_chain.py`, `vectordb.py`, or `processor.py` -- these are exactly the modules the live golden Q/A set exercises end to end:

```bash
pytest -m live
```

## Commit style

Small, focused commits; describe *why* a change was made when it isn't obvious from the diff (a bug's root cause, a tradeoff that was chosen deliberately). Reference the defect/test it fixes where relevant.

## Adding a new season

FTCScout adds a new game each year. Three touchpoints:

1. **`src/data_retrieval.py`** -- add `Stats<year>`/`Score<year>` GraphQL fragments matching the new game's schema (see the existing 2019-2025 fragments for the pattern), and wire the new `MatchScores<year>` inline fragment into the `matches.match.scores` selection.
2. **`src/seasons.py`** -- add the year to `SEASON_NAMES`. This is the single source of truth for both the `/ask` season dropdown and the answer prompt's season label; nothing else needs to change.
3. **A new fixture** -- record a real payload for a team that competed that season (`python scripts/record_fixtures.py --team <n> --season <year>`) and add at least one case to `tests/fixtures/golden/qa_golden.yaml` so the new season is covered by the live answer eval.

## Adding an `extract_info` test case

Add an entry to `tests/fixtures/golden/extract_info_cases.yaml` with a real team number/name verified against `tests/fixtures/teams_index/USIL.json` (or record a bigger index fixture with `scripts/record_fixtures.py --index` if the case needs a name not already in the trimmed set). Run `python scripts/eval_extraction.py` to see precision/recall/per-tag impact before committing.

## Code style

- No comments explaining *what* code does -- names should make that obvious. Comments are for *why*: a non-obvious constraint, a workaround for a specific upstream quirk (e.g. FTCScout's remote-season flat score shape), a tradeoff a future reader would otherwise "fix" back into a bug.
- Prefer small, composable functions over long ones with many branches -- see `processor.py`'s per-chunk-type helpers as the existing pattern.
- New modules should have no side effects at import time beyond what's already established (`config.py` reads env vars at import; `clients.py`'s factories are lazy via `lru_cache`, not eager).
