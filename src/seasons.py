"""Single source of truth for FTC season names.

Both the `/ask` season dropdown (bot.py) and the answer prompt (rag_chain.py)
need this mapping; previously it was hardcoded independently in each place.
"""

SEASON_NAMES = {
    2025: "Decode",
    2024: "Into the Deep",
    2023: "Centerstage",
    2022: "Powerplay",
    2021: "Freight Frenzy",
    2020: "Ultimate Goal",
    2019: "Skystone",
    2018: "Rover Ruckus",
}

CURRENT_SEASON = 2025


def season_name(season: int) -> str:
    return SEASON_NAMES.get(season, f"Season {season}")
