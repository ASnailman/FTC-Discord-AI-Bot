"""Record real FTCScout API responses as offline test fixtures.

This is the only place in the test suite allowed to touch the live API. Run
it by hand whenever a fixture needs to be added or refreshed:

    python scripts/record_fixtures.py --team 14469 --season 2022 --region All
    python scripts/record_fixtures.py --index --region UnitedStates --must-include 14469,9295
    python scripts/record_fixtures.py --chief-delphi "14469 FTC"

Writes deterministic JSON (sorted keys) so re-recording produces a small,
reviewable diff, plus a sibling `.meta.json` with provenance (when it was
recorded and from which query) so a future schema drift is attributable.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from data_retrieval import fetch_team_data, fetch_teams_by_region  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def _write(path: Path, payload, query_name: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    meta = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "api_url": "https://api.ftcscout.org/graphql",
        "query": query_name,
    }
    path.with_suffix(".meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    print(f"wrote {path}")


def record_team(team: int, season: int, region: str, name: str | None):
    data = fetch_team_data(team_number=team, season=season, region=region)
    if data is None:
        print(f"WARNING: fetch_team_data({team}, {season}, {region}) returned None", file=sys.stderr)
    fname = name or f"team_{team}_{season}.json"
    _write(FIXTURES_DIR / "ftcscout" / fname, data, "GetLiterallyEverything")


def record_index(region: str, limit: int, must_include: list[int], out_name: str | None):
    full = fetch_teams_by_region(region)
    if full is None:
        print("WARNING: fetch_teams_by_region returned None", file=sys.stderr)
        return
    full = dict(full)

    must_have_entries = {name: num for name, num in full.items() if num in must_include}
    remaining = {name: num for name, num in full.items() if num not in must_include}

    # keep every colliding name (>1 team sharing a normalized key) and every
    # short single-token name, since those are exactly the extract_info traps
    def norm(n: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", re.sub(r"['\-\._]", "", n.lower())))

    by_norm: dict[str, list[str]] = {}
    for n in remaining:
        by_norm.setdefault(norm(n), []).append(n)
    interesting_names = set()
    for norm_key, names in by_norm.items():
        if len(names) > 1:
            interesting_names.update(names)
        elif " " not in norm_key and len(norm_key) <= 4:
            interesting_names.add(names[0])

    trimmed = dict(must_have_entries)
    for n in interesting_names:
        if len(trimmed) >= limit:
            break
        trimmed[n] = remaining[n]

    for n, num in remaining.items():
        if len(trimmed) >= limit:
            break
        if n not in trimmed:
            trimmed[n] = num

    fname = out_name or f"{region}.json"
    _write(FIXTURES_DIR / "teams_index" / fname, trimmed, "GetTeamsByRegion")
    missing = [t for t in must_include if t not in trimmed.values()]
    if missing:
        print(f"WARNING: must-include teams not found in region {region}: {missing}", file=sys.stderr)


def record_chief_delphi(term: str, name: str | None):
    from tools import discourse

    results = discourse.search(term, limit=10)
    if not results:
        print(f"WARNING: discourse.search({term!r}) returned no posts", file=sys.stderr)
    fname = name or f"{re.sub(r'[^a-z0-9]+', '_', term.lower()).strip('_')}.json"
    _write(FIXTURES_DIR / "chiefdelphi" / fname, results, "chiefdelphi_search")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--team", type=int)
    p.add_argument("--season", type=int)
    p.add_argument("--region", default="All")
    p.add_argument("--name", help="override output filename")
    p.add_argument("--index", action="store_true", help="record a team-name index instead")
    p.add_argument("--limit", type=int, default=400)
    p.add_argument("--must-include", default="", help="comma-separated team numbers to force-keep")
    p.add_argument("--chief-delphi", metavar="TERM", help="record a Chief Delphi search result instead")
    args = p.parse_args()

    if args.chief_delphi:
        record_chief_delphi(args.chief_delphi, args.name)
    elif args.index:
        must = [int(x) for x in args.must_include.split(",") if x.strip()]
        record_index(args.region, args.limit, must, args.name)
    else:
        if args.team is None or args.season is None:
            p.error("--team and --season are required unless --index/--chief-delphi is given")
        record_team(args.team, args.season, args.region, args.name)


if __name__ == "__main__":
    main()
