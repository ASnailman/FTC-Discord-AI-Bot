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


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# --- Multi-source retrieval pipeline ---
# Local sources (stats, chroma) are always on. Everything below is an
# optional node that self-disables when unconfigured, so the bot's default
# out-of-box behavior is identical to before this pipeline existed.

REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "ftc-scouting-bot/0.1")
# Derived, not a literal flag: Reddit is only usable once both creds exist.
ENABLE_REDDIT = bool(REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET)

ENABLE_CHIEF_DELPHI = _env_bool("ENABLE_CHIEF_DELPHI", True)
# Off by default: slowest, least reliable node (web search + captions).
ENABLE_YOUTUBE = _env_bool("ENABLE_YOUTUBE", False)
ENABLE_LLM_ROUTER = _env_bool("ENABLE_LLM_ROUTER", True)

NODE_TIMEOUT_SECONDS = float(os.getenv("NODE_TIMEOUT_SECONDS", "6"))
PIPELINE_BUDGET_SECONDS = float(os.getenv("PIPELINE_BUDGET_SECONDS", "12"))
EXTERNAL_CACHE_TTL_MINUTES = int(os.getenv("EXTERNAL_CACHE_TTL_MINUTES", "60"))

MAX_EXTERNAL_CHARS_PER_SOURCE = int(os.getenv("MAX_EXTERNAL_CHARS_PER_SOURCE", "3000"))
MAX_EXTERNAL_CHARS_TOTAL = int(os.getenv("MAX_EXTERNAL_CHARS_TOTAL", "8000"))

CHIEF_DELPHI_MAX_POSTS = int(os.getenv("CHIEF_DELPHI_MAX_POSTS", "5"))
REDDIT_MAX_POSTS = int(os.getenv("REDDIT_MAX_POSTS", "5"))
YOUTUBE_MAX_VIDEOS = int(os.getenv("YOUTUBE_MAX_VIDEOS", "2"))

# Raised only when external context is actually fused into the prompt
# (rag_chain.ask_bot / chain.answer), so the no-external-sources path keeps
# today's exact token budget and truncation behavior.
GEMINI_MAX_TOKENS_WITH_CONTEXT = int(os.getenv("GEMINI_MAX_TOKENS_WITH_CONTEXT", "2048"))
