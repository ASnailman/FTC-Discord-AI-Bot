# Data model

## FTCScout payload shape

`data_retrieval.fetch_team_data(team_number, season, region)` runs one GraphQL query (`GetLiterallyEverything`) against `https://api.ftcscout.org/graphql` and returns `data.teamByNumber`, shaped roughly:

```
number, name, schoolName, sponsors, rookieYear, website, location{city,state,country,venue}
awards[]      { season, eventCode, type, placement, event{name} }
quickStats    { tot{value,rank}, auto{value,rank}, dc{value,rank}, eg{value,rank} }   # region-scoped
events[]      { season, eventCode, event{code,name,...}, stats{rank,wins,losses,ties,opr{...}} }
matches[]     { season, eventCode, onField, alliance, station, allianceRole,
                match{description,hasBeenPlayed,scores{red{...}, blue{...}}} }
```

Traditional seasons (2019, 2022-2025) key `scores` by alliance color (`red`/`blue`). Remote seasons (2020, 2021 COVID format) return a single flat score object with **no** `red`/`blue` split at all -- `processor._match_scores` detects this by checking for the presence of a `red`/`blue` key rather than assuming the shape.

## Chunk types

`processor.process_team_data(data, season, region)` produces six chunk types per team/season:

| Type | One chunk per | Example text |
|---|---|---|
| `identity` | team | "FTC Team 14469 (HOW). Based in Peoria, IL, USA. Rookie Year: 2018..." |
| `stats` | team (region-scoped OPR) | "Season summary for Team 14469 (HOW): Total OPR 127.5 (Rank #79)..." |
| `award` | award | "Team 14469 (HOW) won the Motivate award (Placement: 2) at the Illinois State Championship..." |
| `event_performance` | event with stats | "At Illinois State Championship (USILCMP), Team 14469 (HOW) ranked #5 with a record of 4-1-0..." |
| `match_granular` | played, on-field match | "Match Q-7 details for Team 14469 (HOW) (Alliance: Red, Station: One, Role: Captain): Total Points: 221..." |
| `season_facts` | team/season (always exactly 1) | Multi-line block: highest/lowest score with attribution, W-L-T, awards, per-event records -- see below. |

## Metadata schema (schema_version 2)

Every chunk's metadata has exactly these keys, all Chroma-legal scalars (no `None`, no nested structures):

| Key | Type | Notes |
|---|---|---|
| `type` | str | one of the six chunk types above |
| `team` | int | |
| `season` | int | the record's own season if present (awards/events/matches can carry their own `season` field independent of the request), else the requested season |
| `region` | str | the region this fetch was scoped to; `"N/A"` if none given |
| `schema_version` | int | currently `2`; see below |
| `fetched_at` | float | unix timestamp, set by `vectordb.upsert_team_data`; drives the current-season cache TTL |
| *(chunk-specific)* | | `award`/`event_performance`/`match_granular` additionally carry `event` (event code); `match_granular` also carries `match` (match description) |

## Chunk id grammar

IDs are content-addressed (derived from the data itself), never a positional index:

```
{team}|{season}|identity
{team}|{season}|{region}|stats
{team}|{season}|award|{eventCode}|{type}|{placement}
{team}|{season}|event|{eventCode}
{team}|{season}|match|{eventCode}|{description}
{team}|{season}|facts
```

`region` appears in the id only for the `stats` chunk, because `quickStats`/OPR is genuinely region-scoped (the GraphQL query takes a `$region` variable for it) while awards/events/matches are not -- putting `region` in every id would duplicate 20-50 match chunks per region the same team happens to be queried under, for no benefit.

Content-addressing (vs. the original `team_{n}_chunk_{i}` positional scheme) is what makes two things work:

- **No cross-season collisions.** A season's chunk count varies (a partial season might have 20 match chunks, a full one 50); a positional scheme silently overwrites the first N chunks of whichever season was written second and strands the rest. A content-addressed id can't collide across seasons because the season is literally in the id.
- **Correct shrink handling.** `VectorDBManager.upsert_team_data` deletes every existing chunk for `(team, season)` before adding the new set (`collection.delete(where=...)` then `collection.add(...)`). If a re-fetch returns fewer matches than before (e.g. a match got voided), the deleted-then-readded set can never leave orphaned chunks behind the way an upsert-only positional scheme would.

## `season_facts`: the deterministic aggregate chunk

`stats.compute_team_season_facts(data, season, region)` computes, in plain Python over the full match/event list: match count, win/loss/tie record, highest and lowest match score (with the event and match code that produced them), mean/median score, season OPR components, award count and list, and per-event rank/record/OPR. `render_facts_block` turns that into the text stored as the `season_facts` chunk and also injected verbatim into the prompt (see [retrieval.md](retrieval.md)).

## `SCHEMA_VERSION` and migrating

`processor.SCHEMA_VERSION` (currently `2`) is stamped onto the Chroma collection's own metadata when it's created. `VectorDBManager.__init__` reads that stamp on every startup and raises `SchemaMismatchError` if it doesn't match the running code's version, rather than silently mixing old- and new-format chunks in the same collection (which is exactly what happened before this schema was introduced -- see [ADR 0001](adr/0001-metadata-filtered-retrieval.md)).

To rebuild after a schema change:

```bash
python scripts/reindex.py --wipe --teams 14469,21333,... --seasons 2022,2024,2025
```
