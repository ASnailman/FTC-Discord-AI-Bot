"""Central configuration, all overridable by environment variable.

Paths are anchored to the project root rather than left relative, so the
bot behaves the same regardless of the process's current working directory
(previously `./chroma_db` only worked when launched from `src/`).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = Path(__file__).resolve().parent

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# When unset, the bot syncs slash commands globally (takes up to ~1h to
# propagate). Set this during development for instant guild-scoped sync.
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID")

CHROMA_PATH = Path(os.getenv("CHROMA_PATH", SRC_ROOT / "chroma_db"))
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "ftc_team_data")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
GEMINI_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.0"))
GEMINI_MAX_TOKENS = int(os.getenv("GEMINI_MAX_TOKENS", "1024"))

RETRIEVAL_K = int(os.getenv("RETRIEVAL_K", "40"))

# Current-season data changes during competition weekends; older seasons are
# immutable once played, so they're cached forever.
CACHE_TTL_HOURS = int(os.getenv("CACHE_TTL_HOURS", "24"))

TEAMS_INDEX_DIR = Path(os.getenv("TEAMS_INDEX_DIR", SRC_ROOT / "data"))
TEAMS_INDEX_TTL_DAYS = int(os.getenv("TEAMS_INDEX_TTL_DAYS", "7"))

DISCORD_MESSAGE_LIMIT = 1900  # Discord hard-caps at 2000; leave headroom.

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
