"""Retrieval + generation: turns a scouting question into a Gemini answer.

Two fixes from the original implementation, both required together (see
docs/retrieval.md for the full rationale):

1. Retrieval is now filtered by the team numbers and season the question was
   asked about (`_build_where`), instead of a global top-k search across
   every team and season ever cached. Filtering requires every chunk to
   carry accurate team/season metadata, which `processor.py`'s schema v2
   now guarantees -- shipping the filter without that would have made
   retrieval find *nothing* instead of the wrong thing.
2. Aggregate questions ("highest score", "how many wins") are answered from
   a deterministic VERIFIED FACTS block (`stats.py`), computed in Python and
   force-included in the prompt, rather than trusting the LLM to do
   arithmetic correctly over a similarity-ranked sample of chunks.

`team_nums=None` reproduces the original unfiltered behavior exactly (used
by `scripts/eval_retrieval.py --mode before` to measure the pre-fix
baseline against the same code path).

`ask_bot` is also the fallback path for `chain.answer` (the multi-source
pipeline in chain.py): whenever no external source has anything to add to a
question, `chain.answer` calls this function completely unchanged, so the
prompt sent to Gemini is byte-for-byte what it always was -- see
tests/unit/test_prompt_compat.py.
"""
from langchain_core.prompts import ChatPromptTemplate
from langchain_classic.chains import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain

import config
from clients import get_llm, get_vector_store
from extraction import extract_info, extract_team_numbers  # noqa: F401  (re-exported)
from nodes.chroma_node import build_where as _build_where  # noqa: F401  (re-exported; see nodes/chroma_node.py)
from nodes.stats_node import facts_block as _facts_block  # noqa: F401  (re-exported; see nodes/stats_node.py)
from seasons import season_name

SYSTEM_PROMPT = (
    "You are an expert FTC (FIRST Tech Challenge) scouting assistant.\n\n"
    "Scope of this answer:\n"
    "- Team(s): {teams}\n"
    "- Season: {season_name} ({season})\n"
    "- Region filter: {region}\n\n"
    "Rules:\n"
    "1. Begin your reply with exactly: [Season: {season_name} {season}, Region: {region}]\n"
    "2. Every specific number, rank, award, and match code you state must come from the "
    "VERIFIED FACTS or CONTEXT below -- never invent one. The VERIFIED FACTS block is "
    "authoritative and already computed; if it answers the question, use its numbers "
    "verbatim rather than recomputing them yourself.\n"
    "3. When citing a match, give the event name and match code together, "
    "e.g. \"Illinois State Championship | Q-7\".\n"
    "4. For hypothetical, comparative, or strategic questions (e.g. \"who would make a good "
    "alliance partner\", \"how would they do against...\"), reason about it and give a real "
    "recommendation using the numbers above as support -- don't refuse just because the "
    "question isn't a direct lookup.\n"
    "5. If the question isn't about FTC teams/events, or no specific team could be "
    "identified, say so briefly (e.g. \"I don't have that data for this question.\") "
    "instead of answering.\n"
    "6. Use whatever format communicates the answer best -- bullet points, bold text, and "
    "multiple paragraphs are all fine. Be thorough rather than terse.\n\n"
    "VERIFIED FACTS:\n{facts}\n\n"
    "CONTEXT:\n{context}"
)


def ask_bot(question: str, team_nums=None, season=None, region=None, k=None) -> str:
    """Answer a scouting question.

    `team_nums`/`season` scope retrieval to the asked team(s)/season via a
    Chroma metadata filter. Passing `team_nums=None` disables filtering
    entirely (the original, unfiltered behavior) -- callers should always
    pass real values; the unfiltered path exists for the before/after eval.
    """
    llm = get_llm()
    vector_store = get_vector_store()

    where = _build_where(team_nums, season)
    # Scale k with team count so a multi-team question doesn't starve later
    # teams of retrieval budget -- each team's own facts block is always
    # force-included regardless, but broader context still benefits from it.
    default_k = config.RETRIEVAL_K * max(1, len(team_nums or []))
    search_kwargs = {"k": k or min(120, default_k)}
    if where:
        search_kwargs["filter"] = where
    retriever = vector_store.as_retriever(search_kwargs=search_kwargs)

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{input}"),
    ]).partial(
        teams=", ".join(str(t) for t in team_nums) if team_nums else "Unknown",
        season=season if season is not None else "Unknown",
        season_name=season_name(season) if season is not None else "Unknown",
        region=region or "Unknown",
        facts=_facts_block(vector_store, team_nums, season),
    )

    question_answer_chain = create_stuff_documents_chain(llm, prompt)
    rag_chain = create_retrieval_chain(retriever, question_answer_chain)

    response = rag_chain.invoke({"input": question})
    return response["answer"]


if __name__ == "__main__":
    from data_retrieval import fetch_teams_by_region

    test_question = "What is team HOW's chances of beating Technophobia, Meta Infinity, and RoboKnights?"
    region_dict = fetch_teams_by_region("USIL")
    print(extract_team_numbers(test_question, region_dict))
