# Testing

## Layers

| Layer | Path | Network? | Runs by default? |
|---|---|---|---|
| Unit | `tests/unit/` | no | yes |
| Integration | `tests/integration/` | no (tmp-path ChromaDB) | yes |
| Eval | `tests/eval/` | no (tmp-path ChromaDB) | yes |
| Live | `tests/live/` | yes -- FTCScout + Gemini | no (`-m live`) |
| External | `tests/external/` | yes -- Chief Delphi/Reddit/YouTube | no (`-m external`) |

```bash
pytest                 # unit + integration + eval, offline, no keys needed
pytest -m live          # live tier only; needs GOOGLE_API_KEY and network
pytest -m external      # external community sources only; no key needed (Reddit self-skips without creds)
pytest -m "not slow"    # skip anything that loads the real sentence-transformer model
```

A bare `pytest` **cannot** touch the network even by accident: every non-`live`/`external` test gets an autouse fixture (`conftest.py:_block_network`) that monkeypatches `requests.post`/`requests.get`/`Session.request`, `httpx.Client.send`/`AsyncClient.send` (the transport `langchain_google_genai`'s Gemini client uses -- confirmed during development that this was a real gap: an offline test calling the LLM router with no mock made a genuine billed Gemini call before this patch existed), and `primp.Client.request`/`AsyncClient.request` (the native HTTP client `ddgs` defaults to) to raise. `live`-marked tests are also auto-skipped unless both `-m live` is passed *and* `GOOGLE_API_KEY` is set (`conftest.py:pytest_collection_modifyitems`); `external`-marked tests are auto-skipped unless `-m external` is passed (no key required -- Chief Delphi needs no auth, and the YouTube/Reddit cases self-skip or need only their own optional credentials), so CI's default job never needs a secret.

## Markers (`pyproject.toml`)

- `live` -- hits FTCScout and/or Gemini.
- `external` -- hits Chief Delphi, Reddit, and/or YouTube (see [nodes.md](nodes.md)).
- `slow` -- would download/run the real `all-MiniLM-L6-v2` model.
- `eval` -- a scored quality benchmark rather than a strict pass/fail unit test.

## Testing the multi-source pipeline

`tests/unit/test_prompt_compat.py` is the regression lock for [adr/0003](adr/0003-multi-source-retrieval-pipeline.md)'s core guarantee: it doesn't re-derive the prompt text, it asserts `chain.answer` calls the literal, unmodified `rag_chain.ask_bot` function whenever there's nothing external to add, and that `chain.EXTENDED_SYSTEM_PROMPT` is provably `rag_chain.SYSTEM_PROMPT` plus an appended section (`str.startswith`), never a rewrite. If this file's tests fail, treat it as seriously as a `test_extract_info_meets_precision_recall_floor` regression -- it means the new pipeline changed behavior for questions it shouldn't have touched.

Each node has its own `tests/unit/test_<source>_node.py` (disabled/empty/ok/error/dedup/cache -- see [nodes.md](nodes.md)'s status table) and its own `tests/unit/test_tools_<source>.py` (the pure I/O adapter, HTTP mocked or a DI'd fake client -- following `tests/integration/test_vectordb.py`'s pattern of injecting a fake rather than patching library internals). `scripts/record_fixtures.py --chief-delphi "<term>"` extends the existing fixture-recording convention to `tests/fixtures/chiefdelphi/`.

`scripts/eval_router.py` scores `nodes.router.route`'s source-selection precision/recall against `tests/fixtures/golden/router_cases.yaml`, the same shape as `scripts/eval_extraction.py`.

## Why a fake embedding function

`tests/support/embeddings.py` hashes tokens into a small deterministic vector instead of using the real sentence-transformer model. This isn't a shortcut that weakens the tests: the bugs this suite targets (missing metadata, wrong filter construction, chunk-id collisions) are embedding-independent -- with a correct `where` filter, retrieval precision is 1.0 regardless of which vectors are used. Avoiding the real model keeps the offline tier fast (no torch import, no 90 MB download) and fully hermetic. The real model is only exercised by the `live` tier, which runs the actual `ask_bot()` pipeline end to end.

## Fixtures

`tests/fixtures/ftcscout/*.json` are real FTCScout API responses, recorded by `scripts/record_fixtures.py` (the only place in the test suite allowed to touch the live API) and committed with a sibling `.meta.json` for provenance (when recorded, from which query). To add or refresh one:

```bash
python scripts/record_fixtures.py --team 14469 --season 2022 --region All
python scripts/record_fixtures.py --index --region UnitedStates --limit 400 --must-include 14469,9295
```

`--must-include` guarantees specific "trap" teams (false-positive-prone names, colliding names) survive the trimming that keeps the committed index fixture small.

`tests/fixtures/golden/extract_info_cases.yaml` is the entity-extraction golden set: `{id, question, expect, forbid, tags}`. Every number in it is a real team verified against `tests/fixtures/teams_index/USIL.json`, not invented. To add a case, add an entry and run:

```bash
python scripts/eval_extraction.py
```

`tests/fixtures/golden/qa_golden.yaml` is the answer-quality golden set: `{id, fixture, team, season, question, expect_type, must_contain, must_not_contain}`. Ground truth strings (e.g. the exact high score) are computed from the fixture by `stats.compute_team_season_facts`, never hand-typed -- see any of the `high_score_*` cases, whose `must_contain` values were generated by running `compute_team_season_facts` against the recorded payload, not guessed.

## Testing /portfolio

`tests/unit/portfolio/` is a separate layer within `tests/unit/` (its own `__init__.py`, same offline guarantees from `conftest.py`'s network guard) covering `ingest`/`extract`/`sanitize`/`vision`/`compose`/`schema`/`render`/`throttle`. `tests/unit/test_bot_portfolio.py` (alongside the other `test_bot_*.py` files, not inside the `portfolio/` subfolder, since it tests `bot.py` itself) covers the command's error paths.

Two things are unique to this layer:

- **No LLM calls, ever, in the offline tier.** `compose.py`'s `get_portfolio_llm` and `vision.py`'s `get_portfolio_llm` are monkeypatched with a `FakeLLM`/`_RecordingStructuredLLM` that returns fixed pydantic instances keyed by which schema `with_structured_output` was bound to -- the same idiom `tests/unit/test_prompt_compat.py` uses for `chain.get_llm_with_context`. `tests/unit/portfolio/test_compose.py` additionally captures every prompt sent, so it can assert hostile uploaded content and hostile `instructions` text land inside their fenced sections, sanitized, never as a live prompt-turn boundary.
- **Runtime-built fixtures, not committed files.** A 1x1 PNG, a text PDF, and an image-only PDF (the shape that matters most -- see `docs/portfolio.md`) are all built at test time in `tests/unit/portfolio/test_extract.py` via a small hand-rolled minimal-PDF builder and Pillow/`python-docx`, rather than committing binary fixtures. Only the XSS payload list in `tests/unit/portfolio/test_render.py` is meaningfully "data," and it's inline in the test file, not a separate fixture.

`tests/live/test_portfolio_live.py` (`-m live`) is the only place `with_structured_output(PortfolioPage)` -- a discriminated-union schema -- is exercised against the real Gemini API; the offline suite can verify our code handles a well-formed response correctly, but not that Gemini actually produces one.

`scripts/eval_portfolio.py --report evals/portfolio.json` scores structural completeness (all six FTC rubric categories represented across pages, no unresolved image references, output under the size cap) against a couple of sample inputs. Like `eval_answers.py`, it hits the real API and is run manually, not part of CI's default job.

## Ratchets

`test_extract_info_meets_precision_recall_floor` (`tests/unit/test_extract_info.py`) asserts a minimum micro-precision (0.95) and micro-recall (0.90) across the whole golden set. This threshold should only ever move up as the extractor improves -- if a change makes it fail, that's a real regression, not a flaky test.
