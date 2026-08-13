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

# --- /portfolio: user-upload-driven engineering portfolio generation ---
# Fully independent of the /ask pipeline above -- see docs/portfolio.md and
# docs/adr/0004-portfolio-generation.md. Off switch kept separate from the
# multi-source pipeline's flags since this is the bot's first feature that
# accepts file uploads and emits HTML, not text.

ENABLE_PORTFOLIO = _env_bool("ENABLE_PORTFOLIO", True)

PORTFOLIO_GEMINI_MODEL = os.getenv("PORTFOLIO_GEMINI_MODEL", GEMINI_MODEL)
PORTFOLIO_GEMINI_TEMPERATURE = float(os.getenv("PORTFOLIO_GEMINI_TEMPERATURE", "0.4"))
PORTFOLIO_GEMINI_MAX_TOKENS = int(os.getenv("PORTFOLIO_GEMINI_MAX_TOKENS", "4096"))

# Upload limits, checked before any file content is read. Defaults are
# effectively "no limit" for a Discord attachment: Discord itself caps
# attachments at 10-500 MB depending on server boost level, well under the
# 1 GB/file, 6 GB/total ceilings here -- these exist as a backstop against
# a pathological value (e.g. a future attachment source without Discord's
# own cap), not as a meaningful restriction in normal use.
PORTFOLIO_MAX_FILES = int(os.getenv("PORTFOLIO_MAX_FILES", "6"))
PORTFOLIO_MAX_FILE_MB = float(os.getenv("PORTFOLIO_MAX_FILE_MB", "1024"))
PORTFOLIO_MAX_TOTAL_MB = float(os.getenv("PORTFOLIO_MAX_TOTAL_MB", "6144"))

# Text-content limits, enforced during extraction.
PORTFOLIO_MAX_INSTRUCTION_CHARS = int(os.getenv("PORTFOLIO_MAX_INSTRUCTION_CHARS", "1500"))
PORTFOLIO_MAX_EXTRACTED_CHARS_PER_FILE = int(os.getenv("PORTFOLIO_MAX_EXTRACTED_CHARS_PER_FILE", "40000"))
PORTFOLIO_MAX_EXTRACTED_CHARS_TOTAL = int(os.getenv("PORTFOLIO_MAX_EXTRACTED_CHARS_TOTAL", "120000"))
PORTFOLIO_MAX_PDF_PAGES = int(os.getenv("PORTFOLIO_MAX_PDF_PAGES", "60"))
PORTFOLIO_MAX_PDF_RENDER_PAGES = int(os.getenv("PORTFOLIO_MAX_PDF_RENDER_PAGES", "8"))

# Image handling: vision-analysis cap, and the longest edge every image is
# downscaled to before embedding or sending to Gemini.
PORTFOLIO_MAX_VISION_IMAGES = int(os.getenv("PORTFOLIO_MAX_VISION_IMAGES", "10"))
PORTFOLIO_IMAGE_MAX_EDGE_PX = int(os.getenv("PORTFOLIO_IMAGE_MAX_EDGE_PX", "1600"))
PORTFOLIO_VISION_TIMEOUT_SECONDS = float(os.getenv("PORTFOLIO_VISION_TIMEOUT_SECONDS", "20"))
PORTFOLIO_VISION_CACHE_TTL_MINUTES = int(os.getenv("PORTFOLIO_VISION_CACHE_TTL_MINUTES", "120"))

# Output size cap (embedded images pushed the HTML over this get downscaled
# further, then dropped, lowest priority first).
PORTFOLIO_MAX_OUTPUT_MB = float(os.getenv("PORTFOLIO_MAX_OUTPUT_MB", "7"))

# Abuse/cost controls: a per-user Discord cooldown (enforced by
# app_commands.checks.cooldown), a per-user rolling daily quota, and a
# process-wide concurrency cap so multiple simultaneous runs can't pile up
# Gemini calls or memory.
PORTFOLIO_COOLDOWN_SECONDS = float(os.getenv("PORTFOLIO_COOLDOWN_SECONDS", "300"))
PORTFOLIO_DAILY_QUOTA = int(os.getenv("PORTFOLIO_DAILY_QUOTA", "5"))
PORTFOLIO_MAX_CONCURRENT = int(os.getenv("PORTFOLIO_MAX_CONCURRENT", "2"))

# Overall wall-clock budget for one generation (ingest through render).
PORTFOLIO_BUDGET_SECONDS = float(os.getenv("PORTFOLIO_BUDGET_SECONDS", "180"))
