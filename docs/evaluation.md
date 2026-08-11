# Evaluation methodology

Three scripts, each runnable in a `before`/`after` mode against the same golden data, so improvement is a measured number rather than an assertion. `before` reproduces the pre-fix code path exactly (not an estimate):

- Extraction: `scripts/_original_extract_info.py` is a verbatim copy of the pre-fix `extract_info`.
- Retrieval/answers: `ask_bot(question, team_nums=None, season=None)` disables the metadata filter entirely, reproducing the original global top-k search through the same, still-current code path.

## `scripts/eval_extraction.py`

Runs the extractor over `tests/fixtures/golden/extract_info_cases.yaml`.

- **micro precision / recall / F1** -- pooled true/false positives across every case.
- **exact-match rate** -- fraction of questions where the extracted set exactly equals the expected set.
- **per-tag breakdown** -- precision/recall broken out by tag (`false_positive_trap`, `collision`, `numeric_guard`, ...), so a regression in one failure category doesn't hide inside a healthy aggregate.
- **confusions** -- for every non-exact-match case, the expected set, the actual set, and the spurious/missed teams, so failures are diagnosable without re-running anything.

## `scripts/eval_retrieval.py`

Builds a mixed corpus (multiple teams, multiple seasons in one collection) with the deterministic hash embedding function, then runs each question in `tests/fixtures/golden/qa_golden.yaml` through the retriever with (`--mode after`) or without (`--mode before`) the metadata filter.

- **team_precision@k / season_precision@k** -- fraction of the k retrieved chunks whose metadata matches the asked team / season.
- **context_purity@k** -- fraction matching *both* (the headline number).
- **facts_chunk_in_topk_rate** -- whether the `season_facts` chunk happens to win similarity ranking on its own. Expected to stay low even after filtering; this is the empirical justification for force-including it by direct id lookup instead (see [retrieval.md](retrieval.md)).
- **avg_foreign_teams_in_context / avg_wasted_context_chars** -- how much of the retrieved context belongs to teams other than the one asked about, and how many characters of prompt budget that costs.

## `scripts/eval_answers.py`

Requires `GOOGLE_API_KEY` and a seeded ChromaDB store (`scripts/reindex.py`). Runs `ask_bot()` against `qa_golden.yaml`, `--runs N` times per question.

- **required_facts_present_rate** -- every `must_contain` string appears in the answer (case-insensitive).
- **forbidden_facts_absent_rate** -- no `must_not_contain` string appears (e.g. the wrong season name, a foreign team number).
- **truncation_rate** -- answer doesn't end in terminal punctuation, a proxy for hitting `max_tokens` or otherwise cutting off mid-sentence.
- **answer_stability** -- across repeat runs of the same question, whether `required_facts_present` agrees every time. Low stability at the original `temperature=0.65` is expected; `temperature=0.0` (current default) should be close to 1.0.
- **p50 / p95 latency**.

## `scripts/eval_router.py`

Not a before/after comparison (there is no pre-existing router to compare against) -- a standalone precision/recall eval for `nodes.router.route`'s source selection against `tests/fixtures/golden/router_cases.yaml`, with `ENABLE_LLM_ROUTER` disabled so the scored behavior is exactly the deterministic rules pass. Same shape as `eval_extraction.py`: micro precision/recall/F1, per-tag breakdown, confusions.

```bash
python scripts/eval_router.py --report evals/after_router.json
```

## `scripts/compare_evals.py`

Takes paired before/after JSON reports and renders a markdown delta table -- see [evaluation-results.md](evaluation-results.md), which is this script's output, committed so the before/after numbers live in the repo rather than only in a terminal that already scrolled away.

## Reproducing the full comparison

```bash
python scripts/reindex.py --wipe --teams 14469,21333,9295,112,20266,9930 --seasons 2022,2024,2025,2021

python scripts/eval_extraction.py --mode before --report evals/before_extraction.json
python scripts/eval_extraction.py --mode after  --report evals/after_extraction.json
python scripts/eval_retrieval.py  --mode before --report evals/before_retrieval.json
python scripts/eval_retrieval.py  --mode after  --report evals/after_retrieval.json
python scripts/eval_answers.py    --mode before --runs 2 --report evals/before_answers.json
python scripts/eval_answers.py    --mode after  --runs 2 --report evals/after_answers.json

python scripts/compare_evals.py \
  evals/before_extraction.json evals/after_extraction.json \
  evals/before_retrieval.json evals/after_retrieval.json \
  evals/before_answers.json evals/after_answers.json \
  --markdown docs/evaluation-results.md
```

## Ratchet policy

`tests/unit/test_extract_info.py::test_extract_info_meets_precision_recall_floor` encodes the extraction thresholds as an actual CI gate (precision >= 0.95, recall >= 0.90). Those numbers should only be raised as the extractor improves, never lowered to make a regression pass.
