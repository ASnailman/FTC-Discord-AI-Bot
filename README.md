# FTC Discord AI Bot

A Discord bot that answers natural-language scouting questions about [FIRST Tech Challenge](https://www.firstinspires.org/robotics/ftc) teams -- match scores, event results, awards, and season stats -- using data from [FTCScout](https://ftcscout.org/) and Google's Gemini.

```
/ask question: How many matches did 21333 win in Into the Deep? season: Into the Deep (2024)

Question: Regarding Team(s) [21333] in the 2024 season in All region: How many
matches did 21333 win in Into the Deep?

Answer: [Season: Into the Deep 2024, Region: All]
Team 21333 (RoboKnights) played 30 matches during the Into the Deep season
and achieved a record of 19-6-0.
```

## What it does

| Command | Description |
|---|---|
| `/ask question season? region?` | Ask about one or more FTC teams. `question` is required; `season` (defaults to the current season) and `region` (defaults to all regions) are optional, with autocomplete. |
| `/ping` | Check the bot's latency. |

`/ask` identifies which team(s) a question refers to (by number or name), fetches and caches their data, and answers using only that team's data for the requested season -- it will not mix in another team's stats or a different season's results. It can also reason about hypothetical, strategic, or comparative questions:

```
/ask question: What are team Technophobia's game strategies?
/ask question: Who is more likely to win a match between team 14469 and The Golden Ratio?
/ask question: What is 21333 known for in the FTC community?
```

For these, the bot goes beyond FTCScout data: it deterministically computes a head-to-head numeric comparison (season OPR, win/loss record, and more, computed in Python, not by the LLM) and pulls in real community context -- Chief Delphi forum posts, Reddit discussion, and YouTube robot-reveal commentary -- when relevant. A plain lookup ("how many matches did 21333 win") never pays any cost for this: it's answered exactly as before, unchanged.

## How it works

1. **Entity extraction** ([src/extraction.py](src/extraction.py)) finds team numbers/names mentioned in the question against a locally cached team-name index.
2. **Fetch + cache** ([src/vectordb.py](src/vectordb.py), [src/data_retrieval.py](src/data_retrieval.py)) pulls each identified team's data from the FTCScout GraphQL API (if not already cached and fresh) and chunks it into ChromaDB with team/season metadata on every chunk.
3. **Routing** ([src/nodes/router.py](src/nodes/router.py)) classifies the question's intent (deterministic rules first, an optional Gemini call only when no rule matches) to decide whether anything beyond FTCScout data is worth fetching.
4. **Retrieval** ([src/rag_chain.py](src/rag_chain.py)) searches ChromaDB filtered to exactly the identified team(s) and season -- never a global search across everyone ever cached.
5. **Deterministic facts** ([src/stats.py](src/stats.py), [src/nodes/stats_node.py](src/nodes/stats_node.py)) precomputes exact aggregates (highest score, win/loss record, award count, and -- for a comparison question -- a cross-team head-to-head table) in Python and injects them into the prompt, so numeric questions don't depend on an LLM doing arithmetic over retrieved chunks.
6. **Community sources** ([src/nodes/](src/nodes), [src/tools/](src/tools)) -- Chief Delphi, Reddit, and YouTube transcripts, run concurrently and bounded by a timeout, sanitized before ever reaching the prompt (see [docs/security.md](docs/security.md)) -- add qualitative context for strategy/reputation/comparison questions only.
7. **Generation** ([src/chain.py](src/chain.py), Gemini via LangChain) answers using the retrieved context, the verified facts block, and (when relevant) community context, grounding every specific number while still allowing reasoning and recommendations for open-ended questions.

See [docs/architecture.md](docs/architecture.md) for the full request lifecycle and a sequence diagram, [docs/retrieval.md](docs/retrieval.md) for the reasoning behind steps 4-5, and [docs/nodes.md](docs/nodes.md) + [docs/adr/0003-multi-source-retrieval-pipeline.md](docs/adr/0003-multi-source-retrieval-pipeline.md) for steps 3 and 6.

## Quick start

**Requirements:** Python 3.12, a Discord bot application, a Gemini API key.

```bash
git clone <this-repo-url>
cd FTC-Discord-AI-Bot
python -m venv .venv
```

Activate the virtual environment:

```bash
# bash / macOS / Linux
source .venv/bin/activate

# PowerShell
.venv\Scripts\Activate.ps1
```

Install dependencies and configure secrets:

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in DISCORD_TOKEN and GOOGLE_API_KEY
```

Run the bot:

```bash
python src/bot.py
```

## Configuration

Set in `.env` (see [.env.example](.env.example) for the full list with defaults):

| Variable | Required | Description |
|---|---|---|
| `DISCORD_TOKEN` | yes | Bot token from the Discord Developer Portal. |
| `GOOGLE_API_KEY` | yes | Gemini API key from [aistudio.google.com](https://aistudio.google.com/apikey). |
| `DISCORD_GUILD_ID` | no | Set during development for instant slash-command sync to one server; omit for global sync (~1 hour to propagate, works everywhere). |
| `CHROMA_PATH`, `EMBEDDING_MODEL`, `GEMINI_MODEL`, `RETRIEVAL_K`, `CACHE_TTL_HOURS`, `TEAMS_INDEX_TTL_DAYS` | no | Tuning knobs; see [src/config.py](src/config.py) for defaults. |
| `ENABLE_CHIEF_DELPHI`, `ENABLE_YOUTUBE`, `REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET`, `ENABLE_LLM_ROUTER`, `NODE_TIMEOUT_SECONDS`, `PIPELINE_BUDGET_SECONDS` | no | Multi-source retrieval pipeline knobs -- see [docs/nodes.md](docs/nodes.md) and [.env.example](.env.example). All default to behavior identical to before this pipeline existed: Chief Delphi on (no auth), YouTube off, Reddit self-disabled without credentials. |

## Create your Discord application & bot

Full walkthrough in [docs/setup-discord.md](docs/setup-discord.md). Summary:

1. Create an application at the [Discord Developer Portal](https://discord.com/developers/applications).
2. **Bot** tab -> Reset Token -> copy it into `DISCORD_TOKEN` (shown only once).
3. **OAuth2 -> URL Generator** -> scopes: `bot` **and** `applications.commands` (both are required -- slash commands never appear with only `bot`). Permissions: Send Messages, Use Application Commands, Embed Links, Read Message History.
4. Open the generated URL and invite the bot to your server.

## Testing

```bash
pytest                    # fast, offline, no API keys needed (default)
pytest -m live             # hits the real FTCScout API and Gemini; needs GOOGLE_API_KEY
pytest -m external         # hits Chief Delphi/Reddit/YouTube; no key needed for Chief Delphi/YouTube
python scripts/eval_extraction.py   # entity-extraction precision/recall
python scripts/eval_router.py       # source-routing precision/recall
python scripts/eval_retrieval.py --mode after   # retrieval purity
python scripts/eval_answers.py --mode after --runs 2   # answer quality (live)
```

See [docs/testing.md](docs/testing.md) for the full test-layer breakdown and [docs/evaluation-results.md](docs/evaluation-results.md) for measured before/after numbers from this hardening pass.

## Project layout

```
src/
  bot.py             Discord slash-command frontend
  extraction.py      Team number/name extraction from free text
  data_retrieval.py  FTCScout GraphQL client + team-index caching
  processor.py       Raw payload -> ChromaDB chunks
  stats.py           Deterministic per-team-season aggregates
  vectordb.py        ChromaDB persistence (schema-versioned, TTL cache)
  rag_chain.py       Filtered retrieval + Gemini generation (direct-lookup path)
  chain.py           Multi-source orchestrator: route, run nodes, fuse, or fall back unchanged
  nodes/             Retrieval node pipeline: router, stats/chroma/chief_delphi/reddit/youtube, fusion
  tools/             Pure I/O adapters for nodes/: http, cache, discourse, reddit, youtube
  clients.py         Process-wide singletons (LLM, embeddings, vector store)
  logging_setup.py   Applies config.LOG_LEVEL to the standard logging module
  config.py, seasons.py, textutils.py
tests/
  unit/, integration/, eval/   offline, run by default
  live/                        hits FTCScout/Gemini, run with `pytest -m live`
  external/                    hits Chief Delphi/Reddit/YouTube, run with `pytest -m external`
  fixtures/, support/, conftest.py
scripts/
  reindex.py, record_fixtures.py, eval_*.py, compare_evals.py
docs/                architecture, data model, retrieval design, node pipeline, security, testing, deployment, ADRs
```

## Data source & attribution

Team, event, match, and award data comes from the [FTCScout](https://ftcscout.org/) public GraphQL API. Strategy/reputation/comparison questions may also pull in public community content from [Chief Delphi](https://www.chiefdelphi.com/), Reddit (r/FTC), and YouTube captions when enabled -- see [docs/nodes.md](docs/nodes.md). This project is not affiliated with FTCScout, Chief Delphi, Reddit, YouTube, or *FIRST*.

## Known limitations

- Entity extraction is English-only and rule-based. A short or ordinary-word team name (like "HOW") only resolves without ALL-CAPS or a "team" prefix if it's otherwise unambiguous; a generic-word team name in plain sentence case (e.g. "java") may or may not resolve correctly -- see [docs/retrieval.md](docs/retrieval.md#known-limitations).
- Team names that differ only by a space (e.g. "Robo Knights" vs "RoboKnights", two different real teams) are only unified in one direction; see the same doc.
- Region filtering affects OPR ranking context but not which team/season data is fetched.
- Community sources are best-effort and often return nothing: Chief Delphi is FRC-leaning (an FTC team's number/name may have zero posts), and most FTC robot-reveal videos have no captions at all. An empty result from these is normal, not a bug -- the bot still answers from FTCScout data alone.
- Community content is opinion, not verified fact, and is presented to the model (and, implicitly, to the user) as such -- see [docs/security.md](docs/security.md) for how it's sanitized and fenced before reaching the prompt.
- The head-to-head comparison table (for "who would win" style questions) is capped at 2-3 teams and is itself best-effort: if any team's FTCScout fetch fails within its short time budget, the comparison is silently omitted rather than shown partial or wrong.

## License

[MIT](LICENSE)
