# Retrieval nodes

See [adr/0003-multi-source-retrieval-pipeline.md](adr/0003-multi-source-retrieval-pipeline.md) for why this exists and what it deliberately isn't (no database, no agentic loop).

## Layout

```
src/
  chain.py                 orchestrator: chain.answer()
  nodes/
    __init__.py             EXTERNAL_NODES registry (name -> node callable)
    base.py                 NodeResult, PipelineState, @retrieval_node, run_nodes()
    router.py                rules + LLM fallback -> RouteDecision
    stats_node.py            wraps stats.py; head-to-head comparison
    chroma_node.py           metadata-filtered retrieval, extracted from rag_chain
    chief_delphi_node.py
    reddit_node.py
    youtube_node.py
    fusion.py                sanitize + fence + budget + render
  tools/
    http.py                  shared requests.Session, timeout, bounded retry
    cache.py                 ~25-line in-process TTL cache
    discourse.py              Chief Delphi Discourse API client
    reddit.py                 PRAW adapter, client injectable
    youtube.py                 ddgs search + youtube-transcript-api fetch
```

`tools/` are pure I/O adapters -- they can raise, take no dependency on the node contract, and are unit-tested with recorded/injected fixtures. `nodes/` wrap a tool with flags, timeouts, and NodeResult rendering; a node function itself never raises.

## The node contract

```python
@dataclass(frozen=True)
class NodeResult:
    source: str          # "stats" | "chroma" | "chief_delphi" | "reddit" | "youtube"
    status: str           # see table below
    text: str = ""         # rendered, prompt-ready text
    citations: tuple = ()   # URLs, shown in the "Sources consulted" footer
    detail: str = ""         # failure reason -- logged server-side, NEVER sent to Discord
```

| Status | Meaning |
|---|---|
| `ok` | Real content, included in the prompt/footer. |
| `empty` | Ran successfully, found nothing -- a normal outcome (e.g. Chief Delphi has no posts about most FTC teams), not an error. |
| `disabled` | Feature flag off / credentials missing. Checked at call time, not registration time. |
| `error` | The underlying call raised; caught by `@retrieval_node`, logged with a traceback, never propagated. |
| `timeout` | Didn't finish within `config.NODE_TIMEOUT_SECONDS` / the pipeline's `config.PIPELINE_BUDGET_SECONDS`. |

Only `ok` results with non-blank text are included by `nodes.fusion.fuse`.

## Orchestration (`chain.py`)

`chain.answer(question, team_nums, season, region, k=None, sources=None, team_names=None)`:

1. Routes the question (`nodes.router.route`) unless `sources=` is given explicitly (used by tests and `scripts/eval_answers.py` for reproducible runs).
2. If no external source is active for this question **and** it isn't a 2+ team question that could produce a head-to-head table, it calls `rag_chain.ask_bot` -- completely unmodified -- and returns. This is the common case and it is byte-identical to the pipeline's pre-existing behavior; see `tests/unit/test_prompt_compat.py`.
3. Otherwise it runs `{stats, chroma, ...active external}` concurrently via `nodes.base.run_nodes`, fuses the external results, and if there's genuinely nothing new (no external content *and* no head-to-head table actually materialized), falls back to step 2's unchanged call anyway.
4. Only when there's real content to add does it build the extended prompt (`chain.EXTENDED_SYSTEM_PROMPT` = `rag_chain.SYSTEM_PROMPT` + two extra rules + an `UNTRUSTED COMMUNITY CONTEXT` section) and call the LLM directly, appending a "Sources consulted" footer.

## Adding a new node

1. Write the I/O in `tools/your_source.py`: functions that can raise, no project-specific imports beyond `config`/`tools.http`.
2. Wrap it in `nodes/your_source_node.py`: a `@retrieval_node("your_source")` function `(state: PipelineState) -> NodeResult`. Check your feature flag first and return `status="disabled"` if unset. Use `tools.cache.TTLCache` if the source is worth caching within a session.
3. Register it in `nodes/__init__.py`'s `EXTERNAL_NODES`.
4. Add it to the relevant `INTENT_SOURCES` entries in `nodes/router.py` (or a new intent) so the router activates it.
5. Add config flags/limits to `src/config.py` and document them in `.env.example`.
6. Tests: a `tests/unit/test_tools_your_source.py` (pure adapter, mocked HTTP), a `tests/unit/test_your_source_node.py` (disabled/empty/ok/error/dedup/cache), and an `@pytest.mark.external` case in `tests/external/test_external_sources_live.py` if the API needs no destructive/paid calls to smoke-test for real.
