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

    documents = [] # The text content for the AI
    metadatas = [] # Searchable tags for ChromaDB

    team_num = data.get('number')
    team_name = data.get('name')

    # --- CHUNK 1: IDENTITY & LOCATION ---
    loc = data.get('location', {}) or {}
    identity_text = (
        f"FTC Team {team_num} is named '{team_name}'. "
        f"Based in {clean_value(loc.get('city'))}, {clean_value(loc.get('state'))}, {clean_value(loc.get('country'))}. "
        f"Rookie Year: {data.get('rookieYear')}. School: {data.get('schoolName', 'Unknown')}."
    )
    documents.append(identity_text)
    metadatas.append({"type": "identity", "team": team_num})

    # --- CHUNK 2: SEASON SUMMARY ---
    qs = data.get('quickStats')
    if qs:
        stats_text = (
            f"Season summary for Team {team_num}: Total OPR {qs.get('tot', {}).get('value', 0):.1f} (Rank #{qs.get('tot', {}).get('rank', 'N/A')}). "
            f"Auto OPR: {qs.get('auto', {}).get('value', 0):.1f}, DC OPR: {qs.get('dc', {}).get('value', 0):.1f}, EG OPR: {qs.get('eg', {}).get('value', 0):.1f}."
        )
        documents.append(stats_text)
        metadatas.append({"type": "stats", "team": team_num})

    # --- CHUNK 3: AWARDS ---
    awards = data.get('awards', [])
    for award in awards:
        award_text = (
            f"Team {team_num} won the {award.get('type')} award (Placement: {award.get('placement')}) "
            f"at the {award.get('event', {}).get('name')} in the {award.get('season')} season."
        )
        documents.append(award_text)
        metadatas.append({"type": "award", "team": team_num, "season": award.get('season')})

    # --- CHUNK 4: EVENT PERFORMANCE ---
    for event_entry in data.get('events', []):
        evt = event_entry.get('event') or {}
        stats = event_entry.get('stats')
        if stats:
            event_text = (
                f"At {evt.get('name')} ({evt.get('code')}), Team {team_num} ranked #{stats.get('rank')} "
                f"with a record of {stats.get('wins')}-{stats.get('losses')}-{stats.get('ties')}. "
                f"Event OPR: {stats.get('opr', {}).get('totalPoints', 0):.1f}."
            )
            documents.append(event_text)
            metadatas.append({"type": "event_performance", "team": team_num, "event": evt.get('code')})

    # --- CHUNK 5: GRANULAR MATCH SCORES ---
    # This section now extracts EVERY field from the scores object in your JSON
    for entry in data.get('matches', []):
        if not entry.get('onField'): continue
        
        match_info = entry.get('match') or {}
        alliance_color = entry.get('alliance').lower()
        scores = match_info.get('scores', {}).get(alliance_color, {})
        
        if scores:
            # Create a detailed breakdown string of all numeric/string scoring fields
            breakdown = ", ".join([f"{k.replace('_', ' ')}: {v}" for k, v in scores.items() if isinstance(v, (int, float, str))])
            
            match_text = (
                f"Match {match_info.get('description')} details for Team {team_num} (Alliance: {alliance_color.capitalize()}): "
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
    print(f"✅ Generated {len(docs)} granular chunks for ChromaDB.")
    # Example of a granular match chunk
    granular_match = [d for d, m in zip(docs, metas) if m['type'] == 'match_granular'][0]
    print(f"\nExample Granular Chunk:\n{granular_match[:200]}...")