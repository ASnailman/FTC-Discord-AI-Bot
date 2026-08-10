"""Live checks against the real FTCScout API.

These exist to catch upstream schema drift early: if FTCScout renames or
removes a field the query relies on, `processor.py` would otherwise fail
silently (a missing key just becomes an absent chunk, not an error).
"""
import json
from pathlib import Path

import pytest

from data_retrieval import fetch_team_data, fetch_teams_by_region

FIXTURE = Path(__file__).parent.parent / "fixtures" / "ftcscout" / "team_14469_2022.json"


def _key_set(obj, prefix=""):
    """Recursively collect dotted key paths from a JSON-shaped object,
    ignoring list contents beyond the first element (schema shape, not data)."""
    keys = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            keys.add(path)
            keys |= _key_set(v, path)
    elif isinstance(obj, list) and obj:
        keys |= _key_set(obj[0], prefix)
    return keys


@pytest.mark.live
def test_fetch_team_data_key_set_matches_fixture():
    live = fetch_team_data(team_number=14469, season=2022, region="All")
    assert live is not None

    with open(FIXTURE, encoding="utf-8") as f:
        fixture = json.load(f)

    live_keys = _key_set(live)
    fixture_keys = _key_set(fixture)

    missing = fixture_keys - live_keys
    assert not missing, f"fields present in the fixture are missing from the live response: {missing}"


@pytest.mark.live
def test_fetch_teams_by_region_returns_name_to_number_map():
    teams = fetch_teams_by_region("USIL")
    assert teams
    assert all(isinstance(v, int) for v in teams.values())


@pytest.mark.live
def test_fetch_team_data_unknown_team_returns_none():
    # Team number far beyond any real registration.
    assert fetch_team_data(team_number=99999999, season=2025, region="All") is None
