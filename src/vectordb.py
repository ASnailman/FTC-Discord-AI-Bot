import chromadb
from chromadb.utils import embedding_functions
from processor import process_team_data
from data_retrieval import fetch_team_data, CURRENT_FTC_SEASON, DEFAULT_REGION

class VectorDBManager:
    def __init__(self, db_path="./chroma_db"):
        self.client = chromadb.PersistentClient(path=db_path)
        self.ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        self.collection = self.client.get_or_create_collection(
            name="ftc_team_data", 
            embedding_function=self.ef
        )

    def is_team_in_db(self, team_num, season, region):
        """Checks if a team already has data in ChromaDB."""
        # We query the DB specifically filtering by the 'team' metadata tag
        results = self.collection.get(
            where={
                "$and": [
                    {"team": team_num},
                    {"season": season},
                    {"region": region}
                ]
            }, 
            include=["metadatas"]
        )
        return len(results['ids']) > 0

    def upsert_team_data(self, raw_data):
        """Processes raw JSON and adds/updates it in the database."""
        team_num = raw_data.get('number')
        docs, metas = process_team_data(raw_data)
        
        if not docs:
            print(f"No documents generated for Team {team_num}.")
            return False

        # Create predictable IDs so we can overwrite them later
        ids = [f"team_{team_num}_chunk_{i}" for i in range(len(docs))]
        
        # upsert = update if exists, insert if it doesn't
        self.collection.upsert(
            documents=docs,
            metadatas=metas,
            ids=ids
        )
        return True

    def get_or_load_team(self, team_num, fetch_function, season=None, region=None):
        """Fetches from DB if exists, otherwise hits API."""
        if season is None:
            season = CURRENT_FTC_SEASON
        if region is None:
            region = DEFAULT_REGION  

        if self.is_team_in_db(team_num, season, region):
            print(f"Team {team_num} (Season {season}) (Region {region}) is already in memory.")
            return True
        else:
            print(f"Fetching Team {team_num} (Season {season}) (Region {region}) from API.")
            raw_data = fetch_function(team_number=team_num, season=season, region=region)
            if raw_data:
                self.upsert_team_data(raw_data)
                return True
            return False

    def get_all_tracked_teams(self):
        """Returns a list of unique (team_number, season) tuples currently in ChromaDB."""
        # Get all metadata tags from the database
        results = self.collection.get(include=["metadatas"])
        
        tracked = set()
        for meta in results.get('metadatas', []):
            if meta:
                team = meta.get('team')
                season = meta.get('season', 2025)
                if team:
                    tracked.add((team, season))
                    
        return list(tracked)

if __name__ == "__main__":
    db = VectorDBManager()
    db.get_or_load_team(14469, fetch_team_data)