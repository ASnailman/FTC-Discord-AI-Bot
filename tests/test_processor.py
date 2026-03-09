import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import pytest
from src.processor import clean_value, process_team_data

# --- TEST 1: The Helper Function ---
def test_clean_value():
    """Ensures our None-handler works correctly."""
    assert clean_value("Peoria") == "Peoria"
    assert clean_value(0) == 0
    assert clean_value(None) == "N/A"

# --- TEST 2: Empty Data Handling ---
def test_process_team_data_empty():
    """Ensures the processor doesn't crash if the API returns empty data."""
    docs, metas = process_team_data({})
    assert docs == []
    assert metas == []

# --- TEST 3: The Chunking Logic ---
def test_process_team_data_valid():
    """Passes a mock JSON payload to ensure chunks and metadata are formatted correctly."""
    
    # 1. Setup: Create a tiny, fake version of FTCScout's JSON
    mock_data = {
        "number": 14469,
        "name": "HOW",
        "location": {
            "city": "Peoria",
            "state": "IL",
            "country": "USA"
        },
        "rookieYear": 2018,
        "matches": [
            {
                "onField": True,
                "alliance": "Red",
                "station": "One",
                "allianceRole": "Captain",
                "match": {
                    "description": "Q-1",
                    "tournamentLevel": "Quals",
                    "scores": {
                        "red": {
                            "totalPoints": 100,
                            "autoHighCones": 3
                        }
                    }
                }
            }
        ]
    }

    # 2. Execution: Run the data through your function
    docs, metas = process_team_data(mock_data)

    # 3. Assertions: Verify the output is exactly what we expect
    
    # We expect 2 chunks: Chunk 1 (Identity) and Chunk 5 (Granular Match)
    assert len(docs) == 2 
    assert len(metas) == 2
    
    # Check the Identity Chunk (Chunk 0)
    assert metas[0]["team"] == 14469
    assert metas[0]["type"] == "identity"
    assert "FTC Team 14469 is named 'HOW'" in docs[0]
    assert "Peoria, IL, USA" in docs[0]

    # Check the Match Chunk (Chunk 1)
    assert metas[1]["type"] == "match_granular"
    assert metas[1]["match"] == "Q-1"
    assert "Total Points: 100" in docs[1]
    assert "autoHighCones: 3" in docs[1]
    assert "Station: One, Role: Captain" in docs[1]

