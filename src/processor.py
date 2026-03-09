import json

def clean_value(value):
    """Helper to handle None or missing values cleanly."""
    return value if value is not None else "N/A"

def process_team_data(data):
    """
    Takes the massive RAW JSON and converts it into a list of 
    'Documents' (Chunks) optimized for ChromaDB.
    """
    if not data:
        return [], []

    documents = [] 
    metadatas = [] 

    team_num = data.get('number')
    team_name = data.get('name')

    # identity, location, sponsors
    loc = data.get('location', {}) or {}
    sponsors = ", ".join(data.get('sponsors', [])) or "None listed"
    identity_text = (
        f"FTC Team {team_num} is named '{team_name}'. "
        f"Based in {clean_value(loc.get('city'))}, {clean_value(loc.get('state'))}, {clean_value(loc.get('country'))} "
        f"at venue: {clean_value(loc.get('venue'))}. "
        f"Rookie Year: {data.get('rookieYear')}. School: {data.get('schoolName', 'Unknown')}. "
        f"Sponsors: {sponsors}. Website: {clean_value(data.get('website'))}."
    )
    documents.append(identity_text)
    metadatas.append({"type": "identity", "team": team_num})

    # season summary
    qs = data.get('quickStats')
    if qs:
        stats_text = (
            f"Season summary for Team {team_num}: Total OPR {qs.get('tot', {}).get('value', 0):.1f} (Rank #{qs.get('tot', {}).get('rank', 'N/A')}) "
            f"across {qs.get('count', 0)} recorded items. "
            f"Auto OPR: {qs.get('auto', {}).get('value', 0):.1f} (Rank #{qs.get('auto', {}).get('rank', 'N/A')}), "
            f"DC OPR: {qs.get('dc', {}).get('value', 0):.1f} (Rank #{qs.get('dc', {}).get('rank', 'N/A')}), "
            f"EG OPR: {qs.get('eg', {}).get('value', 0):.1f} (Rank #{qs.get('eg', {}).get('rank', 'N/A')})."
        )
        documents.append(stats_text)
        metadatas.append({"type": "stats", "team": team_num})

    # awards
    for award in data.get('awards', []):
        person = f" won by {award.get('personName')} " if award.get('personName') else " "
        division = f" (Division: {award.get('divisionName')})" if award.get('divisionName') else ""
        award_text = (
            f"Team {team_num}{person}won the {award.get('type')} award (Placement: {award.get('placement')}){division} "
            f"at the {award.get('event', {}).get('name')} in the {award.get('season')} season."
        )
        documents.append(award_text)
        metadatas.append({"type": "award", "team": team_num, "season": award.get('season'), "event": award.get('eventCode')})

    # event performance and aggregated totals
    for event_entry in data.get('events', []):
        evt = event_entry.get('event') or {}
        stats = event_entry.get('stats')
        if stats:
            # Flatten the 'tot' dictionary containing aggregate event scores
            tot_stats = stats.get('tot', {})
            tot_breakdown = ", ".join([f"{k}: {v}" for k, v in tot_stats.items() if isinstance(v, (int, float, str, bool))])
            
            event_text = (
                f"At {evt.get('name')} ({evt.get('code')}) during the {evt.get('start')} to {evt.get('end')} {evt.get('type')}, "
                f"Team {team_num} ranked #{stats.get('rank')} with a record of {stats.get('wins')} wins, {stats.get('losses')} losses, "
                f"and {stats.get('ties')} ties across {stats.get('qualMatchesPlayed')} qual matches. "
                f"They earned {stats.get('rp')} RP. "
                f"Event OPR Details - Total: {stats.get('opr', {}).get('totalPoints', 0):.1f}, "
                f"Auto: {stats.get('opr', {}).get('autoPoints', 0):.1f}, DC: {stats.get('opr', {}).get('dcPoints', 0):.1f}. "
                f"Aggregate Event Scoring Totals: {tot_breakdown}."
            )
            documents.append(event_text)
            metadatas.append({"type": "event_performance", "team": team_num, "event": evt.get('code')})

    # granular match scores and metadata
    for entry in data.get('matches', []):
        if not entry.get('onField'): continue
        
        match_info = entry.get('match') or {}
        alliance_color = entry.get('alliance').lower()
        scores = match_info.get('scores', {}).get(alliance_color, {})
        
        if scores:
            breakdown = ", ".join([f"{k.replace('_', ' ')}: {v}" for k, v in scores.items() if isinstance(v, (int, float, str, bool))])
            
            meta_text = (
                f"Station: {entry.get('station')}, Role: {entry.get('allianceRole')}, "
                f"Tournament Level: {match_info.get('tournamentLevel')}, Surrogate: {entry.get('surrogate')}, "
                f"DQ: {entry.get('dq')}, No Show: {entry.get('noShow')}."
            )

            match_text = (
                f"Match {match_info.get('description')} details for Team {team_num} (Alliance: {alliance_color.capitalize()}). "
                f"Match Context: {meta_text} "
                f"Total Points: {scores.get('totalPoints')}. Scoring Breakdown: {breakdown}."
            )
            documents.append(match_text)
            metadatas.append({
                "type": "match_granular", 
                "team": team_num, 
                "match": match_info.get('description'),
                "event": entry.get('eventCode')
            })

    return documents, metadatas

if __name__ == "__main__":
    with open('output.json', 'r') as f:
        raw_data = json.load(f)
    docs, metas = process_team_data(raw_data)
    print(docs)
    print(metas)
    print(f"Information chunks created, ready for ChromaDB.")