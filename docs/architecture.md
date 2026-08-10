# Architecture

## Request lifecycle

See [../diagram.md](../diagram.md) for the sequence diagram. In prose:

1. A user runs `/ask question:"..." season:... region:...` in Discord. `bot.py` immediately calls `interaction.response.defer()` -- Gemini and FTCScout calls can take longer than Discord's 3-second interaction timeout.
2. `extraction.extract_info` scans the question against a locally cached team-name index (`data_retrieval.get_cached_teams_by_region`) and returns the team numbers it found, with provenance (matched by number or by name).
3. If no team was identified, the bot replies with a short refusal and never calls the LLM.
4. For each identified team, `vectordb.VectorDBManager.get_or_load_team` checks whether that team+season is already cached and fresh (TTL-gated for the current season); on a miss it fetches from FTCScout, chunks the payload (`processor.process_team_data`), and upserts into ChromaDB.
5. `rag_chain.ask_bot` retrieves chunks filtered to exactly the identified team(s) and season, force-includes the precomputed facts chunk for each team, and calls Gemini with both in the prompt.
6. The bot replies, chunked under Discord's 2000-character limit if needed.

## Module responsibilities

| Module | Responsibility |
|---|---|
| `bot.py` | Discord I/O: slash commands, autocomplete, response formatting, async offloading of blocking calls. |
| `extraction.py` | Turns free text into a list of team numbers with match provenance. No I/O. |
| `data_retrieval.py` | FTCScout GraphQL client; also owns the on-disk team-name index cache. |
| `processor.py` | Raw FTCScout JSON -> `(documents, metadatas, ids)` for ChromaDB. No I/O. |
| `stats.py` | Deterministic aggregate computation (`compute_team_season_facts`) and its text rendering (`render_facts_block`). No I/O. |
| `vectordb.py` | ChromaDB persistence: schema versioning, cache-hit/TTL logic, delete-before-add upserts. |
| `rag_chain.py` | Builds the metadata filter, the prompt, and drives the LangChain retrieval + generation chain. |
| `clients.py` | Process-wide singletons (embeddings model, LLM, Chroma client/vector store) so they're constructed once, not per request. |
| `config.py`, `seasons.py`, `textutils.py` | Shared constants and small formatting helpers. |

## Threading model

`discord.py` runs a single asyncio event loop. Every blocking call in the pipeline (`requests.post` to FTCScout, ChromaDB reads/writes, the sentence-transformer encode, the Gemini call) is wrapped in `asyncio.to_thread(...)` in `bot.py` so it runs on a worker thread instead of blocking the event loop -- otherwise one slow `/ask` would stall the whole bot, including `/ping` and Discord's own heartbeat.

ChromaDB's `PersistentClient` is not safe for concurrent writers, so `bot.py` serializes upserts across simultaneous `/ask` invocations with an `asyncio.Lock`.

`clients.warm_up()` runs once in `setup_hook` (also off the event loop) so the sentence-transformer model is loaded before the first real request, not during it.

## Storage

- **ChromaDB** (`src/chroma_db/`, gitignored) is the only persistent store. One collection, `ftc_team_data`, holds every chunk for every team/season ever fetched. A `schema_version` tag on the collection's own metadata lets `VectorDBManager` refuse to read a collection written by an incompatible chunk schema instead of silently misbehaving -- see [data-model.md](data-model.md).
- **Team-name index cache** (`src/data/teams_index_<region>.json`, gitignored) is a plain JSON file with a 7-day TTL, so `/ask` doesn't re-download FTCScout's full team list (up to ~19,000 rows for region `All`) on every invocation.

There is no relational database in the running application. An earlier `src/sqlite_db/` directory built a `team_number -> team_name` SQLite table but nothing at runtime ever read it; it was removed rather than fixed, since the JSON index cache above already solves the same problem more simply.
