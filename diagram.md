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
    participant RAG as rag_chain.py
    end

    box External APIs
    participant FTCScout as FTCScout GraphQL
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

    Frontend->>RAG: ask_bot(question, team_nums=[21333], season, region)
    RAG->>VDB: vector_store.get(ids=["21333|<season>|facts"])
    VDB-->>RAG: VERIFIED FACTS block (deterministic aggregates)
    RAG->>VDB: retriever.invoke(question, filter={team:21333, season:...})
    VDB-->>RAG: top-k chunks, all belonging to 21333/<season>
    RAG->>Gemini: system prompt (facts + filtered context) + question
    Gemini-->>RAG: answer, grounded only in this team/season
    RAG-->>Frontend: answer text
    Frontend-->>User: "Team 21333 (RoboKnights) won 19 of 30 matches..."
```

See [docs/architecture.md](docs/architecture.md) for the full request lifecycle and module responsibilities, and [docs/retrieval.md](docs/retrieval.md) for why retrieval is filtered and why aggregate answers come from a precomputed facts block rather than the LLM.
