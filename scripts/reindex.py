"""Rebuild the ChromaDB vector store under the current chunk schema.

The store shipped with this repo was written by an older `processor.py`
(pre schema-versioning, pre season-aware chunk ids) and also carries an
orphaned `ftc_data` collection nothing references anymore. `VectorDBManager`
refuses to read a collection whose `schema_version` doesn't match, so this
script is how you get back to a working store:

    python scripts/reindex.py --wipe --teams 14469,21333,9295 --seasons 2022,2024,2025

`--wipe` deletes both collections before rebuilding. Without it, existing
data for teams/seasons not listed is left alone (useful for topping up).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import chromadb  # noqa: E402

import config  # noqa: E402
from data_retrieval import fetch_team_data  # noqa: E402
from vectordb import VectorDBManager  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--wipe", action="store_true", help="delete existing collections before rebuilding")
    p.add_argument("--teams", required=True, help="comma-separated team numbers")
    p.add_argument("--seasons", required=True, help="comma-separated seasons")
    p.add_argument("--region", default="All")
    args = p.parse_args()

    teams = [int(t) for t in args.teams.split(",") if t.strip()]
    seasons_list = [int(s) for s in args.seasons.split(",") if s.strip()]

    client = chromadb.PersistentClient(path=str(config.CHROMA_PATH))

    if args.wipe:
        for collection in client.list_collections():
            print(f"Deleting collection '{collection.name}'...")
            client.delete_collection(collection.name)

    manager = VectorDBManager(client=client)

    for team in teams:
        for season in seasons_list:
            print(f"Fetching team {team}, season {season}, region {args.region}...")
            raw = fetch_team_data(team_number=team, season=season, region=args.region)
            if not raw:
                print(f"  -> no data returned, skipping")
                continue
            manager.upsert_team_data(raw, season=season, region=args.region)
            count = manager.collection.get(
                where={"$and": [{"team": team}, {"season": season}]}
            )
            print(f"  -> {len(count['ids'])} chunks")

    print(f"\nTotal chunks in '{config.CHROMA_COLLECTION}': {manager.collection.count()}")


if __name__ == "__main__":
    main()
