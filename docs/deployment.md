# Deployment

This is a single always-on process (`python src/bot.py`) holding a persistent connection to Discord's gateway -- it needs a long-running host, not a request/response serverless function.

## Persistent state

Two directories must survive restarts and (if you ever run more than one replica) must not be shared/raced between processes:

- `src/chroma_db/` -- the vector store. Losing it means every cached team re-fetches from FTCScout on next use; not catastrophic, but a stateful volume avoids the cold-start cost.
- `src/data/` -- the team-name index cache. Losing it just means one extra FTCScout call to rebuild it.

Both are already gitignored; mount them as a persistent volume in whatever you deploy to, or point `CHROMA_PATH`/`TEAMS_INDEX_DIR` at a volume path via environment variables (see `.env.example`).

## Model cache

`sentence-transformers` downloads `all-MiniLM-L6-v2` (~90 MB) from Hugging Face on first use and caches it under `~/.cache/huggingface`. In a container, either bake the model into the image at build time or mount a persistent cache directory (`HF_HOME`) so a redeploy doesn't re-download it.

## Example: systemd unit

```ini
[Unit]
Description=FTC Discord AI Bot
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/ftc-bot/FTC-Discord-AI-Bot
EnvironmentFile=/opt/ftc-bot/FTC-Discord-AI-Bot/.env
ExecStart=/opt/ftc-bot/FTC-Discord-AI-Bot/.venv/bin/python src/bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Example: Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENV CHROMA_PATH=/data/chroma_db
ENV TEAMS_INDEX_DIR=/data/teams_index
ENV HF_HOME=/data/hf_cache
VOLUME ["/data"]

CMD ["python", "src/bot.py"]
```

Run with `.env` supplied at container start (`--env-file .env`), and a volume mounted at `/data` for the three paths above.

## Logging

`config.LOG_LEVEL` (default `INFO`) is applied by `logging_setup.configure()`, called once from `bot.py` at import time. The retrieval node pipeline (`nodes/`, `tools/`) and `bot.py`'s error handlers use `logging.getLogger(__name__)` throughout, so node failures, timeouts, and unhandled `/ask` errors show up as structured log lines rather than being silently swallowed or printed. Some pre-existing modules (`vectordb.py`, `data_retrieval.py`) still use `print()` for their own operational messages -- unchanged from before this pipeline, since converting them wasn't required by this work.

## Network egress

Beyond FTCScout and Gemini, the bot now optionally reaches `chiefdelphi.com` (on by default, no auth), `reddit.com`/OAuth (only if `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET` are set), and DuckDuckGo + `youtube.com` for caption fetches (only if `ENABLE_YOUTUBE=true`). If deploying behind an egress firewall, allow these hosts or leave the corresponding source disabled -- every node self-disables cleanly (`status="disabled"`) rather than failing the whole request when its host is unreachable, though an unreachable-but-enabled host will instead surface as `status="error"`/`"timeout"` after its budget expires (`NODE_TIMEOUT_SECONDS`/`PIPELINE_BUDGET_SECONDS`).

## Secrets

`DISCORD_TOKEN` and `GOOGLE_API_KEY` must never be committed. `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET`, if you enable the Reddit source, are the same category of secret. `.env` is gitignored; in a hosted environment, prefer your platform's secret manager (systemd `EnvironmentFile` with restricted permissions, Docker secrets, or your cloud provider's secret store) over baking them into an image or committing an `.env` file anywhere, including private repos.
