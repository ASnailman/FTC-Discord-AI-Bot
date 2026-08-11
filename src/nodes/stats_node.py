"""Stats Node: wraps the existing deterministic facts pipeline.

There is no `ftc_data.db` and no relational database in the running
application (see docs/architecture.md and docs/adr/0003) -- the numeric
facts a "stats node" would otherwise query for (OPR, auto/DC/EG OPR,
win/loss record, event placements) are already computed exactly by
`stats.compute_team_season_facts` and force-included in every prompt per
ADR 0002. This module is that mechanism, extracted so it fits the same
node contract as the new external sources; it is not a new data source.

`facts_block` is `rag_chain._facts_block`, moved here verbatim --
`rag_chain._facts_block` re-exports it so nothing about that module's
public surface changes.

`render_head_to_head` is new: ADR 0002 deliberately left cross-team
comparison out of scope ("the facts block is season/team-scoped, not
cross-team"). For a 2-3 team comparison question, this fetches each team's
raw FTCScout data (the same client `vectordb.get_or_load_team` already
uses) and runs it through the same `compute_team_season_facts` -- still
100%-deterministic Python, never LLM arithmetic -- to build a side-by-side
table. It is strictly best-effort and time-boxed on its own short budget
independent of the node's overall timeout: if it can't finish quickly, the
per-team VERIFIED FACTS blocks (the guaranteed part) are still returned
untouched, just without the comparison table appended.
"""
import concurrent.futures

import data_retrieval
from clients import get_vector_store
from logging_setup import get_logger
from nodes.base import NodeResult, PipelineState, STATUS_EMPTY, STATUS_OK, retrieval_node
from stats import compute_team_season_facts
from textutils import fmt

logger = get_logger(__name__)

_MAX_COMPARISON_TEAMS = 3
_HEAD_TO_HEAD_BUDGET_SECONDS = 4.0

# Marker prefix identifying head-to-head content within the rendered facts
# text -- chain.py checks for this substring to decide whether a comparison
# table was actually produced (rather than duplicating the fetch/compute
# just to find out), since a failed fetch means `render_head_to_head`
# degrades to "" and the marker simply won't be present.
HEAD_TO_HEAD_MARKER = "Head-to-head comparison"

# (facts key, display label, higher-is-better)
_COMPARISON_AXES = [
    ("season_opr", "Season OPR", True),
    ("auto_opr", "Auto OPR", True),
    ("dc_opr", "DC/Teleop OPR", True),
    ("eg_opr", "Endgame OPR", True),
    ("mean_points", "Avg match score", True),
]


def facts_block(vector_store, team_nums, season) -> str:
    """Force-include the precomputed facts chunk for every asked team, so
    aggregate answers never depend on winning similarity ranking."""
    if not team_nums or season is None:
        return "No verified facts available (no specific team/season identified)."
    ids = [f"{t}|{season}|facts" for t in team_nums]
    result = vector_store.get(ids=ids, include=["documents"])
    docs = result.get("documents") or []
    if not docs:
        return "No verified facts available for the requested team(s)/season."
    return "\n\n".join(docs)


def _fetch_facts_dict(team_num, season, region):
    """Live FTCScout fetch + compute -- used only by head-to-head rendering,
    which needs numeric values rather than `facts_block`'s pre-rendered
    text. Not persisted to Chroma: the existing `season_facts` chunk
    already covers single-team lookups, this is purely for the ephemeral
    comparison render. Returns None on any failure."""
    try:
        raw = data_retrieval.fetch_team_data(team_number=team_num, season=season, region=region)
    except Exception:
        logger.exception("head-to-head: fetch_team_data failed for team %s", team_num)
        return None
    if not raw:
        return None
    return compute_team_season_facts(raw, season, region)


def _fetch_facts_dicts_bounded(team_nums, season, region, budget_seconds):
    """Fetches every team's facts dict in parallel, bounded by a single
    overall budget so a slow/unreachable FTCScout call can never make the
    always-on stats node blow past its own timeout in run_nodes.

    Deliberately NOT a `with ThreadPoolExecutor(...)` block -- its __exit__
    calls `shutdown(wait=True)` unconditionally, which would silently
    re-block on the very threads this function is trying to stop waiting
    for. `executor.shutdown(wait=False)` below must be the only shutdown
    call (mirrors nodes.base.run_nodes, which has the same constraint)."""
    results = {}
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(team_nums))
    futures = {executor.submit(_fetch_facts_dict, t, season, region): t for t in team_nums}
    try:
        for future in concurrent.futures.as_completed(futures, timeout=budget_seconds):
            team = futures[future]
            try:
                results[team] = future.result(timeout=0.01)
            except Exception:
                results[team] = None
    except concurrent.futures.TimeoutError:
        logger.warning("head-to-head fetch exceeded its %.1fs budget; using partial results", budget_seconds)
    finally:
        executor.shutdown(wait=False)
    return [results.get(t) for t in team_nums]


def _axis_value(facts: dict, key: str):
    return facts.get(key)


def render_head_to_head(facts_list: list) -> str:
    """Deterministic cross-team comparison table. `facts_list` is a list of
    `stats.compute_team_season_facts` dicts (Nones are dropped); returns
    "" if fewer than 2 usable dicts remain, so callers can append the
    result unconditionally."""
    facts_list = [f for f in facts_list if f]
    if len(facts_list) < 2:
        return ""

    lines = [f"{HEAD_TO_HEAD_MARKER} (computed directly from FTCScout data, not estimated):"]
    lines.append(" vs ".join(f"Team {f['team']} ({f.get('name') or 'Unknown'})" for f in facts_list))

    for key, label, higher_is_better in _COMPARISON_AXES:
        values = [_axis_value(f, key) for f in facts_list]
        if all(v is None for v in values):
            continue
        rendered = ", ".join(
            f"Team {f['team']}: {fmt(v) if v is not None else 'N/A'}" for f, v in zip(facts_list, values)
        )
        numeric = [(f["team"], v) for f, v in zip(facts_list, values) if v is not None]
        edge = ""
        if len(numeric) >= 2:
            best_team, _ = (max if higher_is_better else min)(numeric, key=lambda tv: tv[1])
            edge = f" (edge: Team {best_team})"
        lines.append(f"- {label}: {rendered}{edge}")

    lines.append(
        "- Record (W-L-T): "
        + ", ".join(f"Team {f['team']}: {f['wins']}-{f['losses']}-{f['ties']}" for f in facts_list)
    )
    lines.append(
        "- Awards won: " + ", ".join(f"Team {f['team']}: {f['award_count']}" for f in facts_list)
    )

    return "\n".join(lines)


@retrieval_node("stats")
def stats_node(state: PipelineState) -> NodeResult:
    vector_store = get_vector_store()
    text = facts_block(vector_store, state.team_nums, state.season)

    if 2 <= len(state.team_nums) <= _MAX_COMPARISON_TEAMS and state.season is not None:
        try:
            facts_dicts = _fetch_facts_dicts_bounded(
                state.team_nums, state.season, state.region, _HEAD_TO_HEAD_BUDGET_SECONDS,
            )
            head_to_head = render_head_to_head(facts_dicts)
            if head_to_head:
                text = f"{text}\n\n{head_to_head}"
        except Exception:
            # Best-effort enrichment only -- the per-team facts_block above
            # is the guaranteed part and must never be lost because of this.
            logger.exception("head-to-head comparison failed; continuing with per-team facts only")

    status = STATUS_OK if (state.team_nums and state.season is not None) else STATUS_EMPTY
    return NodeResult(source="stats", status=status, text=text)
