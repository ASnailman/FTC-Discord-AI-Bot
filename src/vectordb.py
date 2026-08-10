"""ChromaDB persistence layer.

Two things changed from the original implementation, both load-bearing:

1. `is_team_in_db` used to filter on a `region` metadata field that
   `processor.py` never wrote, so it always returned False -- every `/ask`
   re-fetched and re-embedded every mentioned team regardless of whether it
   was already cached. It now checks team+season only (region doesn't
   affect what data was fetched for a team/season, only the OPR ranking
   context, which is itself stored per-chunk), plus a TTL for the
   still-changing current season.
2. Chunk ids used to be `team_{n}_chunk_{i}` -- a plain enumeration index
   with no season component. Re-upserting a smaller payload for a
   different season silently overwrote the first N chunks and stranded the
   rest under indices the new payload didn't reach. `upsert_team_data` now
   deletes every existing chunk for that team+season before adding the new
   ones, so a shrinking payload can never leave orphans behind.
"""
import time

import chromadb
from chromadb.utils import embedding_functions

import config
import seasons
from data_retrieval import DEFAULT_REGION
from processor import SCHEMA_VERSION, process_team_data


class SchemaMismatchError(RuntimeError):
    """Raised when an existing collection was written by a different chunk schema."""


def build_where(**clauses):
    """Build a Chroma `where` filter. Chroma requires `$and`/`$or` to wrap
    at least two operands, so a single clause is passed through bare."""
    parts = [{k: v} for k, v in clauses.items() if v is not None]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return {"$and": parts}


class VectorDBManager:
    def __init__(self, db_path=None, embedding_function=None, client=None):
        if client is not None:
            self.client = client
        else:
            path = str(db_path or config.CHROMA_PATH)
            self.client = chromadb.PersistentClient(path=path)

        self.ef = embedding_function or embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=config.EMBEDDING_MODEL
        )
        self.collection = self._get_or_create_collection()

    def _get_or_create_collection(self):
        name = config.CHROMA_COLLECTION
        existing = {c.name for c in self.client.list_collections()}
        if name in existing:
            collection = self.client.get_collection(name=name, embedding_function=self.ef)
            stored_version = (collection.metadata or {}).get("schema_version")
            if stored_version != SCHEMA_VERSION:
                raise SchemaMismatchError(
                    f"Collection '{name}' was written with schema_version={stored_version!r}, "
                    f"but processor.py is at {SCHEMA_VERSION}. "
                    "Run `python scripts/reindex.py --wipe` to rebuild it."
                )
            return collection
        return self.client.create_collection(
            name=name, embedding_function=self.ef, metadata={"schema_version": SCHEMA_VERSION},
        )

    def is_team_in_db(self, team_num: int, season: int) -> bool:
        """Checks if a team/season already has data in ChromaDB."""
        results = self.collection.get(
            where=build_where(team=team_num, season=season), limit=1, include=["metadatas"],
        )
        if not results["ids"]:
            return False

        if season == seasons.CURRENT_SEASON:
            fetched_at = (results["metadatas"][0] or {}).get("fetched_at")
            if fetched_at is None:
                return False
            age_hours = (time.time() - fetched_at) / 3600
            if age_hours > config.CACHE_TTL_HOURS:
                return False

        return True

    def upsert_team_data(self, raw_data, season, region=None) -> bool:
        """Processes raw JSON and replaces this team/season's chunks in the database."""
        team_num = raw_data.get("number")
        docs, metas, ids = process_team_data(raw_data, season=season, region=region)

        if not docs:
            print(f"No documents generated for Team {team_num}.")
            return False

        fetched_at = time.time()
        for meta in metas:
            meta["fetched_at"] = fetched_at

        # Delete-before-add: guarantees a shrinking payload (e.g. fewer
        # matches than last time) doesn't leave stranded chunks behind.
        self.collection.delete(where=build_where(team=team_num, season=season))
        self.collection.add(documents=docs, metadatas=metas, ids=ids)
        return True

    def get_or_load_team(self, team_num, fetch_function, season=None, region=None) -> bool:
        """Fetches from DB if cached and fresh, otherwise hits the API."""
        if season is None:
            season = seasons.CURRENT_SEASON
        if region is None:
            region = DEFAULT_REGION

        if self.is_team_in_db(team_num, season):
            return True

        raw_data = fetch_function(team_number=team_num, season=season, region=region)
        if raw_data:
            return self.upsert_team_data(raw_data, season=season, region=region)
        return False


if __name__ == "__main__":
    from data_retrieval import fetch_team_data

    db = VectorDBManager()
    db.get_or_load_team(14469, fetch_team_data, season=2022)
