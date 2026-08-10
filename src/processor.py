"""Converts a raw FTCScout team payload into ChromaDB-ready chunks.

Every chunk gets a content-addressed id and complete metadata
(team/season/region/type/schema_version). This is what makes retrieval
filterable by team+season (see rag_chain.py) and makes re-upserting a
smaller payload correctly drop stale chunks (see vectordb.py).
"""
from stats import compute_team_season_facts, render_facts_block
from textutils import clean_value, fmt

SCHEMA_VERSION = 2


def _meta(team_num, season, region, chunk_type, **extra):
    meta = {
        "type": chunk_type,
        "team": team_num,
        "season": season,
        "region": region,
        "schema_version": SCHEMA_VERSION,
    }
    for key, value in extra.items():
        meta[key] = clean_value(value)
    return meta


def _match_scores(match_info, alliance):
    """Return the score dict for this alliance, handling remote-season payloads.

    Traditional seasons key scores by alliance color (`{"red": {...}, "blue": {...}}`).
    Remote seasons (2020/2021 COVID format) return a single flat score object
    with no red/blue split at all.
    """
    scores_obj = match_info.get("scores") or {}
    if "red" in scores_obj or "blue" in scores_obj:
        return scores_obj.get(alliance) or {}
    return scores_obj


_BREAKDOWN_EXCLUDE = {"totalPoints", "totalPointsNp"}
_BREAKDOWN_EXCLUDE_PREFIXES = ("penaltyPointsByOpp", "minorsByOpp", "majorsByOpp")


def _score_breakdown(scores: dict) -> str:
    parts = []
    for key, value in scores.items():
        if key in _BREAKDOWN_EXCLUDE or key.startswith(_BREAKDOWN_EXCLUDE_PREFIXES):
            continue
        if not isinstance(value, (int, float, str)):
            continue
        if isinstance(value, (int, float)) and value == 0:
            continue
        parts.append(f"{key.replace('_', ' ')}: {value}")
    return ", ".join(parts)


def process_team_data(data, season, region=None):
    """
    Takes the raw FTCScout JSON for one team/season and converts it into
    parallel (documents, metadatas, ids) lists ready for ChromaDB.

    `season` is the season the caller requested this data for (used as the
    metadata/id season whenever a record doesn't carry its own). `region` is
    the region this fetch was scoped to (only meaningful for the `stats`
    chunk, since quickStats/OPR are region-relative).
    """
    if not data:
        return [], [], []

    region = region or "N/A"

    documents = []
    metadatas = []
    ids = []

    team_num = data.get("number")
    team_name = data.get("name", "Unknown Name")
    team_id_string = f"Team {team_num} ({team_name})"

    # identity, location, sponsors
    loc = data.get("location") or {}
    identity_text = (
        f"FTC {team_id_string}. "
        f"Based in {clean_value(loc.get('city'))}, {clean_value(loc.get('state'))}, {clean_value(loc.get('country'))}. "
        f"Rookie Year: {clean_value(data.get('rookieYear'))}. School: {data.get('schoolName') or 'Unknown'}."
    )
    documents.append(identity_text)
    metadatas.append(_meta(team_num, season, region, "identity"))
    ids.append(f"{team_num}|{season}|identity")

    # season summary (region-scoped OPR/rank)
    qs = data.get("quickStats")
    if qs:
        tot = qs.get("tot") or {}
        auto = qs.get("auto") or {}
        dc = qs.get("dc") or {}
        eg = qs.get("eg") or {}
        stats_text = (
            f"Season summary for {team_id_string}: Total OPR {fmt(tot.get('value'))} "
            f"(Rank #{clean_value(tot.get('rank'))}). "
            f"Auto OPR: {fmt(auto.get('value'))}, DC OPR: {fmt(dc.get('value'))}, EG OPR: {fmt(eg.get('value'))}."
        )
        documents.append(stats_text)
        metadatas.append(_meta(team_num, season, region, "stats"))
        ids.append(f"{team_num}|{season}|{region}|stats")

    # awards
    for award in data.get("awards", []):
        award_season = award.get("season") or season
        award_event_code = award.get("eventCode") or "unknown"
        award_type = award.get("type") or "unknown"
        placement = award.get("placement")
        award_text = (
            f"{team_id_string} won the {award.get('type')} award (Placement: {clean_value(placement)}) "
            f"at the {(award.get('event') or {}).get('name')} in the {award_season} season."
        )
        documents.append(award_text)
        metadatas.append(_meta(team_num, award_season, region, "award", event=award_event_code))
        ids.append(f"{team_num}|{award_season}|award|{award_event_code}|{award_type}|{clean_value(placement)}")

    # event performance and aggregated totals
    for event_entry in data.get("events", []):
        evt = event_entry.get("event") or {}
        stats = event_entry.get("stats")
        if not stats:
            continue
        event_season = event_entry.get("season") or season
        opr = stats.get("opr") or {}
        event_text = (
            f"At {evt.get('name')} ({evt.get('code')}), {team_id_string} ranked #{clean_value(stats.get('rank'))} "
            f"with a record of {clean_value(stats.get('wins'))}-{clean_value(stats.get('losses'))}-{clean_value(stats.get('ties'))}. "
            f"Event OPR: {fmt(opr.get('totalPoints'))}."
        )
        documents.append(event_text)
        metadatas.append(_meta(team_num, event_season, region, "event_performance", event=evt.get("code")))
        ids.append(f"{team_num}|{event_season}|event|{evt.get('code')}")

    # granular match scores and metadata
    for entry in data.get("matches", []):
        if not entry.get("onField"):
            continue
        match_info = entry.get("match") or {}
        if not match_info.get("hasBeenPlayed"):
            continue

        alliance = (entry.get("alliance") or "").lower()
        scores = _match_scores(match_info, alliance)
        if not scores:
            continue

        match_season = entry.get("season") or season
        breakdown = _score_breakdown(scores)
        alliance_label = alliance.capitalize() if alliance else "N/A"
        station = clean_value(entry.get("station"))
        role = clean_value(entry.get("allianceRole"))

        match_text = (
            f"Match {match_info.get('description')} details for {team_id_string} "
            f"(Alliance: {alliance_label}, Station: {station}, Role: {role}): "
            f"Total Points: {scores.get('totalPoints')}. Scoring Breakdown: {breakdown}."
        )
        documents.append(match_text)
        metadatas.append(_meta(
            team_num, match_season, region, "match_granular",
            match=match_info.get("description"), event=entry.get("eventCode"),
        ))
        ids.append(f"{team_num}|{match_season}|match|{entry.get('eventCode')}|{match_info.get('description')}")

    # deterministic aggregate facts (bypasses LLM arithmetic over context chunks)
    facts = compute_team_season_facts(data, season, region)
    documents.append(render_facts_block(facts))
    metadatas.append(_meta(team_num, season, region, "season_facts"))
    ids.append(f"{team_num}|{season}|facts")

    return documents, metadatas, ids


if __name__ == "__main__":
    import json

    with open("../tests/fixtures/ftcscout/team_14469_2022.json") as f:
        raw_data = json.load(f)
    docs, metas, ids = process_team_data(raw_data, season=2022, region="All")
    print(f"{len(docs)} chunks generated, ready for ChromaDB.")
