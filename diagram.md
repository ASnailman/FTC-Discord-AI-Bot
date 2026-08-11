```mermaid
sequenceDiagram
    autonumber

    box Discord
    actor User
    participant Frontend as Discord.py (bot.py)
    end

    box Application
    participant Extract as extraction.py
    participant VDB as vectordb.py
    participant Chain as chain.py
    participant Router as nodes/router.py
    participant RAG as rag_chain.py
    end

    box External APIs
    participant FTCScout as FTCScout GraphQL
    participant Community as Chief Delphi / Reddit / YouTube
    participant Gemini as Gemini
    end

    User->>Frontend: /ask "How many matches did 21333 win in Into the Deep?"
    Frontend->>Frontend: defer() the interaction

    Frontend->>Extract: extract_info(question, cached team index)
    Extract-->>Frontend: [(21333, "21333", "number")]

    alt no team identified
        Frontend-->>User: "I couldn't identify a team..." (refusal, no LLM call)
    end

    loop for each identified team
        Frontend->>VDB: get_or_load_team(21333, season, region)
        VDB->>VDB: is_team_in_db? (team+season+TTL check)
        alt cache miss or stale
            VDB->>FTCScout: fetch_team_data(21333, season, region)
            FTCScout-->>VDB: raw JSON
            VDB->>VDB: process_team_data() -> chunks incl. season_facts
            VDB->>VDB: delete old team+season chunks, add new ones
        end
    end

    Frontend->>Chain: answer(question, team_nums=[21333], season, region)
    Chain->>Router: route(question)
    Router-->>Chain: RouteDecision(sources)

    alt direct lookup -- no external source needed
        Chain->>RAG: ask_bot(question, team_nums, season, region)  [byte-identical, unchanged]
        RAG->>VDB: vector_store.get(ids=["21333|<season>|facts"])
        VDB-->>RAG: VERIFIED FACTS block (deterministic aggregates)
        RAG->>VDB: retriever.invoke(question, filter={team:21333, season:...})
        VDB-->>RAG: top-k chunks, all belonging to 21333/<season>
        RAG->>Gemini: system prompt (facts + filtered context) + question
        Gemini-->>RAG: answer, grounded only in this team/season
        RAG-->>Chain: answer text
    else strategy / reputation / comparison ("who beats X", "what's their strategy")
        par nodes run concurrently, each budgeted
            Chain->>Community: chief_delphi / reddit / youtube nodes
            Community-->>Chain: sanitized posts/transcripts (or "empty" -- a normal outcome)
        and
            Chain->>VDB: stats + chroma nodes (facts, filtered context, optional head-to-head)
            VDB-->>Chain: facts + context text
        end
        Chain->>Chain: fuse() -- sanitize, fence, budget external text
        Chain->>Gemini: extended prompt (facts + context + UNTRUSTED COMMUNITY CONTEXT)
        Gemini-->>Chain: answer
        Chain->>Chain: append "Sources consulted" footer
    end

    Chain-->>Frontend: answer text
    Frontend-->>User: reply (allowed_mentions disabled -- see docs/security.md)
```

See [docs/architecture.md](docs/architecture.md) for the full request lifecycle and module responsibilities, [docs/retrieval.md](docs/retrieval.md) for why retrieval is filtered and why aggregate answers come from a precomputed facts block rather than the LLM, and [docs/nodes.md](docs/nodes.md) + [docs/adr/0003-multi-source-retrieval-pipeline.md](docs/adr/0003-multi-source-retrieval-pipeline.md) for the routing/community-source branch.
