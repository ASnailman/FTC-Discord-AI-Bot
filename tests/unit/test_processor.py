from processor import process_team_data
from textutils import clean_value, fmt


# --- clean_value / fmt ---

def test_clean_value_passthrough():
    assert clean_value("Peoria") == "Peoria"
    assert clean_value(0) == 0


def test_clean_value_none_becomes_na():
    assert clean_value(None) == "N/A"


def test_fmt_formats_float():
    assert fmt(127.542) == "127.5"


def test_fmt_none_becomes_na():
    assert fmt(None) == "N/A"


# --- empty / null payloads ---

def test_empty_payload_returns_empty():
    docs, metas, ids = process_team_data({}, season=2025, region="All")
    assert docs == []
    assert metas == []
    assert ids == []


def test_none_payload_returns_empty():
    docs, metas, ids = process_team_data(None, season=2025, region="All")
    assert docs == []
    assert metas == []
    assert ids == []


# --- real fixture: team 14469 / 2022 (Powerplay) ---

def test_chunk_count_and_types(payload_14469_2022):
    docs, metas, ids = process_team_data(payload_14469_2022, season=2022, region="All")
    # 1 identity + 1 stats + 3 awards + 5 events + 29 matches + 1 facts
    assert len(docs) == 40
    assert len(metas) == 40
    assert len(ids) == 40
    types = [m["type"] for m in metas]
    assert types.count("identity") == 1
    assert types.count("stats") == 1
    assert types.count("award") == 3
    assert types.count("event_performance") == 5
    assert types.count("match_granular") == 29
    assert types.count("season_facts") == 1


def test_identity_chunk(payload_14469_2022):
    docs, metas, _ = process_team_data(payload_14469_2022, season=2022, region="All")
    assert "FTC Team 14469 (HOW)." in docs[0]
    assert "Peoria, IL, USA" in docs[0]
    assert "Rookie Year: 2018" in docs[0]
    assert metas[0] == {
        "type": "identity", "team": 14469, "season": 2022, "region": "All", "schema_version": 2,
    }


def test_identity_chunk_survives_null_location():
    data = {"number": 1, "name": "X", "location": None}
    docs, metas, _ = process_team_data(data, season=2025, region="All")
    assert "N/A, N/A, N/A" in docs[0]


def test_stats_chunk(payload_14469_2022):
    docs, metas, ids = process_team_data(payload_14469_2022, season=2022, region="All")
    stats_doc = docs[1]
    assert "Total OPR 127.5 (Rank #79)" in stats_doc
    assert "Auto OPR: 37.2, DC OPR: 81.7, EG OPR: 18.5" in stats_doc
    assert metas[1]["type"] == "stats"
    assert ids[1] == "14469|2022|All|stats"


def test_stats_chunk_absent_when_quickstats_missing():
    data = {"number": 1, "name": "X"}
    docs, metas, _ = process_team_data(data, season=2025, region="All")
    assert "stats" not in [m["type"] for m in metas]


def test_award_chunks(payload_14469_2022):
    docs, metas, ids = process_team_data(payload_14469_2022, season=2022, region="All")
    award_docs = [d for d, m in zip(docs, metas) if m["type"] == "award"]
    assert len(award_docs) == 3
    assert any("Motivate" in d and "Placement: 2" in d and "Illinois State Championship" in d for d in award_docs)
    award_metas = [m for m in metas if m["type"] == "award"]
    assert all(m["season"] == 2022 for m in award_metas)


def test_award_chunk_null_season_falls_back_to_requested():
    data = {
        "number": 1, "name": "X",
        "awards": [{"type": "Think", "placement": 1, "season": None, "eventCode": "E1", "event": {"name": "Ev"}}],
    }
    docs, metas, ids = process_team_data(data, season=2025, region="All")
    award_meta = next(m for m in metas if m["type"] == "award")
    assert award_meta["season"] == 2025
    assert "2025 season" in next(d for d, m in zip(docs, metas) if m["type"] == "award")


def test_event_performance_chunks(payload_14469_2022):
    docs, metas, _ = process_team_data(payload_14469_2022, season=2022, region="All")
    event_docs = [d for d, m in zip(docs, metas) if m["type"] == "event_performance"]
    assert len(event_docs) == 5
    cmp_doc = next(d for d in event_docs if "USILCMP" in d)
    assert "ranked #5" in cmp_doc
    assert "4-1-0" in cmp_doc
    assert "104.3" in cmp_doc


def test_event_chunk_survives_null_opr(payload_9930_2025_sparse):
    docs, metas, _ = process_team_data(payload_9930_2025_sparse, season=2025, region="All")
    event_docs = [d for d, m in zip(docs, metas) if m["type"] == "event_performance"]
    assert any("N/A" in d and "Event OPR" in d for d in event_docs)


def test_stats_chunk_survives_null_quickstats_values(payload_9930_2025_sparse):
    docs, metas, _ = process_team_data(payload_9930_2025_sparse, season=2025, region="All")
    stats_doc = next(d for d, m in zip(docs, metas) if m["type"] == "stats")
    assert "Total OPR N/A" in stats_doc
    assert "Rank #N/A" in stats_doc


def test_match_chunks_skip_off_field(payload_14469_2022):
    total_entries = len(payload_14469_2022["matches"])
    docs, metas, _ = process_team_data(payload_14469_2022, season=2022, region="All")
    match_docs = [d for d, m in zip(docs, metas) if m["type"] == "match_granular"]
    assert total_entries == 33
    assert len(match_docs) == 29


def test_match_chunk_content(payload_14469_2022):
    docs, metas, ids = process_team_data(payload_14469_2022, season=2022, region="All")
    q7 = next(d for d, m in zip(docs, metas) if m["type"] == "match_granular" and m.get("match") == "Q-7")
    assert "Total Points: 221" in q7
    assert "autoHighCones: 5" in q7
    assert "Alliance: Red" in q7
    assert "Station: One" in q7
    assert "Role: Captain" in q7


def test_match_chunk_null_alliance_does_not_crash():
    data = {
        "number": 1, "name": "X",
        "matches": [{
            "onField": True, "alliance": None, "eventCode": "E1", "station": "One", "allianceRole": "Captain",
            "match": {"description": "Q-1", "hasBeenPlayed": True, "scores": {"totalPoints": 50}},
        }],
    }
    docs, metas, _ = process_team_data(data, season=2025, region="All")
    match_docs = [d for d, m in zip(docs, metas) if m["type"] == "match_granular"]
    assert len(match_docs) == 1
    assert "Total Points: 50" in match_docs[0]


def test_match_chunks_skip_unplayed():
    data = {
        "number": 1, "name": "X",
        "matches": [{
            "onField": True, "alliance": "Red", "eventCode": "E1",
            "match": {"description": "Q-1", "hasBeenPlayed": False, "scores": {"red": {"totalPoints": 50}}},
        }],
    }
    docs, metas, _ = process_team_data(data, season=2025, region="All")
    assert "match_granular" not in [m["type"] for m in metas]


def test_remote_season_flat_scores_are_extracted(payload_20266_2021_remote):
    """Remote-season matches have a flat score object (no red/blue key)."""
    docs, metas, _ = process_team_data(payload_20266_2021_remote, season=2021, region="All")
    match_docs = [d for d, m in zip(docs, metas) if m["type"] == "match_granular"]
    assert len(match_docs) > 0
    flat_match = next(d for d in match_docs if "CABCNVS3" in d or any(
        "CABCNVS3" == m.get("event") for m in metas if m["type"] == "match_granular"
    ))
    assert "Total Points:" in flat_match


# --- ids and metadata invariants (the D2/D13 regression lock) ---

def test_ids_are_unique(payload_14469_2022):
    _, _, ids = process_team_data(payload_14469_2022, season=2022, region="All")
    assert len(set(ids)) == len(ids)


def test_every_metadata_value_is_chroma_scalar(payload_14469_2022, payload_20266_2021_remote, payload_9930_2025_sparse):
    for payload, season in [(payload_14469_2022, 2022), (payload_20266_2021_remote, 2021), (payload_9930_2025_sparse, 2025)]:
        _, metas, _ = process_team_data(payload, season=season, region="All")
        for meta in metas:
            for key, value in meta.items():
                assert value is not None, f"{key} is None in {meta}"
                assert isinstance(value, (str, int, float, bool)), f"{key}={value!r} is not a Chroma scalar"


def test_every_chunk_carries_team_season_region_type(payload_14469_2022):
    _, metas, _ = process_team_data(payload_14469_2022, season=2022, region="All")
    for meta in metas:
        assert isinstance(meta["team"], int)
        assert isinstance(meta["season"], int)
        assert isinstance(meta["region"], str)
        assert isinstance(meta["type"], str)


def test_season_facts_chunk_is_present_and_accurate(payload_14469_2022):
    docs, metas, ids = process_team_data(payload_14469_2022, season=2022, region="All")
    facts_doc = next(d for d, m in zip(docs, metas) if m["type"] == "season_facts")
    assert "306 points in F-1" in facts_doc
    assert "Matches played: 29" in facts_doc
    assert ids[-1] == "14469|2022|facts"
