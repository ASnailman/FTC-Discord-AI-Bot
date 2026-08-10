"""Deterministic per-team-season aggregate facts.

Questions like "what was team X's highest score" or "how many matches did X
win" need an exact answer computed over ALL of a team's matches/events, not
a similarity-ranked sample of them. `compute_team_season_facts` computes
those aggregates directly from the raw FTCScout payload in Python (100%
recall, zero ambiguity); `render_facts_block` turns them into the short,
authoritative text block that gets force-included in every prompt for the
teams being asked about, bypassing the LLM's need to do arithmetic over
retrieved chunks at all.
"""
import statistics

from textutils import fmt


def _match_score(entry):
    """Return (points, event_code, description) for one on-field, played match, or None."""
    if not entry.get("onField"):
        return None
    match_info = entry.get("match") or {}
    if not match_info.get("hasBeenPlayed"):
        return None

    alliance = (entry.get("alliance") or "").lower()
    scores_obj = match_info.get("scores") or {}
    if "red" in scores_obj or "blue" in scores_obj:
        # Traditional season: alliance-keyed score objects.
        scores = scores_obj.get(alliance) or {}
    else:
        # Remote season (2020/2021 COVID format): score object is flat,
        # with no red/blue split.
        scores = scores_obj

    points = scores.get("totalPoints")
    if not isinstance(points, (int, float)):
        return None
    return (points, entry.get("eventCode"), match_info.get("description"))


def compute_team_season_facts(data, season, region=None) -> dict:
    """Compute exact per-season aggregates from a raw FTCScout team payload."""
    if not data:
        return {}

    event_name_by_code = {}
    event_records = []
    wins = losses = ties = 0
    for event_entry in data.get("events", []):
        evt = event_entry.get("event") or {}
        if evt.get("code"):
            event_name_by_code[evt["code"]] = evt.get("name")
        stats = event_entry.get("stats")
        if not stats:
            continue
        wins += stats.get("wins") or 0
        losses += stats.get("losses") or 0
        ties += stats.get("ties") or 0
        event_records.append({
            "event_code": evt.get("code"),
            "event_name": evt.get("name"),
            "rank": stats.get("rank"),
            "wins": stats.get("wins"),
            "losses": stats.get("losses"),
            "ties": stats.get("ties"),
            "opr_total": (stats.get("opr") or {}).get("totalPoints"),
        })

    match_points = [
        m for m in (_match_score(e) for e in data.get("matches", [])) if m is not None
    ]

    awards = data.get("awards") or []
    qs = data.get("quickStats") or {}

    facts = {
        "team": data.get("number"),
        "name": data.get("name"),
        "season": season,
        "region": region,
        "match_count": len(match_points),
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "award_count": len(awards),
        "awards": [
            {
                "type": a.get("type"),
                "placement": a.get("placement"),
                "event": (a.get("event") or {}).get("name"),
            }
            for a in awards
        ],
        "events": event_records,
        "season_opr": (qs.get("tot") or {}).get("value"),
        "season_opr_rank": (qs.get("tot") or {}).get("rank"),
        "auto_opr": (qs.get("auto") or {}).get("value"),
        "dc_opr": (qs.get("dc") or {}).get("value"),
        "eg_opr": (qs.get("eg") or {}).get("value"),
    }

    if match_points:
        high = max(match_points, key=lambda m: m[0])
        low = min(match_points, key=lambda m: m[0])
        pts = [m[0] for m in match_points]
        facts["high_score"] = {
            "points": high[0], "event_code": high[1],
            "event_name": event_name_by_code.get(high[1]), "match": high[2],
        }
        facts["low_score"] = {
            "points": low[0], "event_code": low[1],
            "event_name": event_name_by_code.get(low[1]), "match": low[2],
        }
        facts["mean_points"] = round(sum(pts) / len(pts), 1)
        facts["median_points"] = statistics.median(pts)
    else:
        facts["high_score"] = None
        facts["low_score"] = None
        facts["mean_points"] = None
        facts["median_points"] = None

    return facts


def render_facts_block(facts: dict) -> str:
    """Render computed facts into the VERIFIED FACTS prompt block."""
    if not facts:
        return "No verified facts available for this team/season."

    header = f"Team {facts['team']} ({facts.get('name') or 'Unknown'}) - Season {facts['season']}"
    if facts.get("region"):
        header += f", Region {facts['region']}"
    lines = [header + ":"]

    if facts.get("match_count"):
        hs, ls = facts["high_score"], facts["low_score"]
        lines.append(
            f"- Matches played: {facts['match_count']}. "
            f"Record: {facts['wins']}-{facts['losses']}-{facts['ties']} (summed across events)."
        )
        lines.append(
            f"- Highest match score: {hs['points']} points in {hs['match']} "
            f"at {hs['event_name'] or hs['event_code']}."
        )
        lines.append(
            f"- Lowest match score: {ls['points']} points in {ls['match']} "
            f"at {ls['event_name'] or ls['event_code']}."
        )
        lines.append(
            f"- Average match score: {fmt(facts['mean_points'])}. "
            f"Median: {fmt(facts['median_points'])}."
        )
    else:
        lines.append("- No played matches recorded.")

    if facts.get("season_opr") is not None:
        lines.append(
            f"- Season OPR: {fmt(facts['season_opr'])} (rank #{facts.get('season_opr_rank', 'N/A')}). "
            f"Auto OPR: {fmt(facts.get('auto_opr'))}, DC OPR: {fmt(facts.get('dc_opr'))}, "
            f"EG OPR: {fmt(facts.get('eg_opr'))}."
        )

    lines.append(f"- Awards won: {facts['award_count']}.")
    for a in facts.get("awards", []):
        lines.append(f"  - {a['type']} (Placement {a['placement']}) at {a['event']}.")

    for e in facts.get("events", []):
        lines.append(
            f"- At {e['event_name'] or e['event_code']}: ranked #{e['rank']}, "
            f"record {e['wins']}-{e['losses']}-{e['ties']}, event OPR {fmt(e['opr_total'])}."
        )

    return "\n".join(lines)
