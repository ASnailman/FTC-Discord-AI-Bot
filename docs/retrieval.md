# Retrieval design

## Why metadata filtering

The original retriever ran a plain top-40 cosine similarity search over the *entire* ChromaDB collection -- every team, every season, ever cached in that process's lifetime -- with no filter at all, even though the team number(s) and season being asked about were already known by that point in the request. A question about team 14469's 2022 season could retrieve team 21333's 2024 match chunks purely because they happened to be semantically similar generic scouting text ("Match Q-7 details... Total Points: ...").

Measured on a realistic mixed corpus (multiple teams, multiple seasons in one collection, mirroring production):

| Metric | Unfiltered (before) | Filtered (after) |
|---|---|---|
| Team precision@40 | 0.593 | 1.0 |
| Season precision@40 | 0.379 | 1.0 |
| Context purity@40 (both) | 0.257 | 1.0 |
| Avg. foreign teams pulled into context | 2.0 | 0.0 |

See [evaluation-results.md](evaluation-results.md) for the full, reproducible numbers including the downstream effect on actual Gemini answers.

The fix is a Chroma `where` filter built from the extracted team number(s) and season, passed to `as_retriever(search_kwargs={"k": ..., "filter": where})`:

```python
# single team:   {"team": 14469}
# multiple:      {"team": {"$in": [14469, 21333]}}
# + season:      {"$and": [{"team": ...}, {"season": 2022}]}
```

Chroma requires `$and`/`$or` to wrap at least two operands -- a single clause is passed through bare (`rag_chain._build_where`).

**Sequencing note:** this filter only works because every chunk's metadata reliably carries `team` and `season` (schema v2, see [data-model.md](data-model.md)). Shipping the filter *before* that metadata fix would have made retrieval return almost nothing instead of the wrong thing, since only ~6% of chunks in the original store carried a `season` tag at all.

## Why aggregate answers don't come from retrieval at all

Filtering alone doesn't fix everything. "What was 14469's highest score in Powerplay?" needs the true maximum over *every* match chunk for that team/season -- not whichever handful happen to rank highest by cosine similarity, which is close to arbitrary for chunks that are all near-duplicate "Match X details... Total Points: N" strings. A team with more matches than `k` (real example: team 21333/2024 has 30 match chunks; some teams have 50+ across a full season) can't even guarantee full recall from retrieval, regardless of how good the filter is.

Instead, `stats.compute_team_season_facts` computes exact aggregates in Python (highest/lowest score with attribution, win/loss record, award count, per-event records) and `vectordb` stores the rendered result as a `season_facts` chunk. `rag_chain.ask_bot` fetches that chunk **directly by id** (`vector_store.get(ids=[f"{team}|{season}|facts"])`) before building the retrieval chain at all -- its presence in the prompt never depends on winning similarity ranking or fitting inside `k`. The system prompt tells the model these numbers are authoritative and it must not recompute them:

> The VERIFIED FACTS block is authoritative and already computed. If it answers the question, use its numbers verbatim -- do not add, average, or compare numbers yourself.

See [ADR 0002](adr/0002-deterministic-facts-over-llm-arithmetic.md) for the alternatives considered (a plain summary chunk, a tool-calling loop) and why this was simpler and more reliable than either.

## The system prompt

```
You are an expert FTC (FIRST Tech Challenge) scouting assistant.

Scope of this answer:
- Team(s): {teams}
- Season: {season_name} ({season})
- Region filter: {region}

Rules:
1. Begin your reply with exactly: [Season: {season_name} {season}, Region: {region}]
2. Every specific number, rank, award, and match code you state must come from the
   VERIFIED FACTS or CONTEXT below -- never invent one. The VERIFIED FACTS block is
   authoritative and already computed; if it answers the question, use its numbers
   verbatim rather than recomputing them yourself.
3. When citing a match, give the event name and match code together...
4. For hypothetical, comparative, or strategic questions (e.g. "who would make a good
   alliance partner", "how would they do against..."), reason about it and give a real
   recommendation using the numbers above as support -- don't refuse just because the
   question isn't a direct lookup.
5. If the question isn't about FTC teams/events, or no specific team could be
   identified, say so briefly instead of answering.
6. Use whatever format communicates the answer best -- bullet points, bold text, and
   multiple paragraphs are all fine. Be thorough rather than terse.

VERIFIED FACTS:
{facts}

CONTEXT:
{context}
```

Two defects in the original prompt this replaces: (1) Python string-literal concatenation silently dropped spaces/newlines at several joins, so the resolved prompt actually read `...Region: IL]If referencing...Match-9Context:\n{context}` with words run together; (2) it *demanded* the model state the season and region in its reply while no retrieved chunk text ever contained either -- the model had no honest way to satisfy rule 1 and would guess. The rewritten prompt binds `season`/`season_name`/`region` via `ChatPromptTemplate.partial(...)`, so they're always present as real values, not something the model has to infer from context.

`temperature` was also dropped from the original `0.65` to `0.0` (`config.GEMINI_TEMPERATURE`) and `max_tokens` raised from `500` to `1024` -- a factual scouting lookup shouldn't have creative variance, and 500 tokens was truncating longer answers mid-sentence.

**Note on scope vs. tone.** An earlier version of this prompt also capped answers at 6 sentences, banned markdown, and instructed the model to answer *only* from retrieved data or refuse. That over-corrected: it made the bot unable to answer hypothetical/analytical questions ("which teams would make good alliance partners for X") that the original bot handled well. The current prompt keeps the hard constraint narrow -- specific numbers must be real and never invented (rule 2) -- while explicitly permitting reasoning, recommendations, and rich formatting on top of those numbers (rules 4 and 6).

## Entity extraction: context-clue overrides

The single-token stoplist gate (below) is necessary to stop "How many matches did 21333 win?" from matching the team named "HOW" (14469), but a blanket gate also blocks "HOW" when the user genuinely means the team. `extraction._has_team_context_signal` adds two narrow overrides, checked against the *original, case-preserving* text:

| Signal | Example | Resolves? |
|---|---|---|
| Token is ALL-CAPS, and the whole question isn't shouted | `"How does HOW compare to the top teams?"` | yes -> 14469 |
| Token is immediately preceded by "team"/"teams"/"named" | `"How good is team ERA"` | yes -> 12847 |
| Neither signal present, ordinary sentence case | `"How many matches did 21333 win?"` | no match on "how" |
| Whole question is uppercase (signal suppressed) | `"HOW MANY MATCHES DID 21333 WIN?"` | no match on "how" |

A possessive suffix (`"HOW's chances"`) is stripped before tokenization (`extraction._POSSESSIVE_RE`) so it doesn't fuse into an unmatchable `"hows"` token, independent of these signals.

## Known limitations

- **Single-token ambiguity without a context signal.** A one-token name that's short or a common word only matches if it carries one of the two context signals above, or is at least 4 characters and not a common English/FTC-domain word. A generic-word team name like "java" that appears in ordinary sentence case with no "team" prefix and isn't ALL-CAPS can't be reliably disambiguated from the ordinary word -- this is an accepted, documented tradeoff rather than something the rule-based extractor can resolve without an LLM disambiguation step (not currently implemented, to avoid an extra round-trip on every `/ask`).
- **Numeric matching is region-independent by design.** The original code only accepted a bare number as a team number if it appeared in the (region-limited) name index being searched -- so a team outside the queried region could never be matched by number at all, even when explicitly typed. Numbers are now validated by shape (3-6 digits, or 1-2 digits with an explicit `team`/`#` prefix, excluding bare 4-digit numbers that look like a season year) instead of by index membership. The tradeoff: an ordinary 3-6 digit number in a sentence ("there are 500 teams this year") could in principle be misread as a team number; in practice this is rare in scouting questions and no case in the golden test set triggers it.
- **Spacing-variant unification is one-directional.** "Robo Knights" and "RoboKnights" are two different real teams (9295/16609 and 9930/33862 respectively) that happen to differ only by a space. Multi-token names are indexed under both their spaced and concatenated forms, so a *concatenated or hyphenated* query ("roboknights", "Robo-Knights") returns the union of all four teams. A *spaced* query ("Robo Knights") only returns the teams that are natively spelled with a space, because there's no reliable way to guess where a space belongs inside a single already-concatenated token. This is documented behavior, not a bug -- see `extraction.build_name_index` and the `spacing_union` test cases in `tests/fixtures/golden/extract_info_cases.yaml`.
