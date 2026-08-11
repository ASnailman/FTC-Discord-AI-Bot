"""Chroma Node: metadata-filtered retrieval (ADR 0001), extracted from
`rag_chain.ask_bot` so it fits the same node contract as the new external
sources -- its retrieval semantics (the `where` filter, `k` scaling) are
unchanged. `rag_chain._build_where` re-exports `build_where` so existing
importers (`scripts/eval_retrieval.py`, `tests/eval/test_retrieval_precision.py`)
are unaffected.

`rag_chain.ask_bot` still drives retrieval through LangChain's
`create_retrieval_chain`/`create_stuff_documents_chain` directly, not
through `chroma_node` -- that's what lets `chain.answer` fall back to it
unchanged (byte-identical prompt) whenever no external source has anything
to add. `chroma_node` exists for the *other* case: when `chain.answer` is
building a fused, multi-source prompt by hand and needs Chroma's context as
plain text alongside the other sources.
"""
import config
from clients import get_vector_store
from nodes.base import NodeResult, PipelineState, STATUS_EMPTY, STATUS_OK, retrieval_node


def build_where(team_nums, season):
    """Chroma requires $and/$or to wrap at least two operands."""
    clauses = []
    if team_nums:
        nums = [int(t) for t in team_nums]
        clauses.append({"team": {"$in": nums}} if len(nums) > 1 else {"team": nums[0]})
    if season is not None:
        clauses.append({"season": int(season)})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def get_retriever(team_nums, season, k=None):
    """Builds the same filtered retriever `rag_chain.ask_bot` has always used."""
    vector_store = get_vector_store()
    where = build_where(team_nums, season)
    default_k = config.RETRIEVAL_K * max(1, len(team_nums or []))
    search_kwargs = {"k": k or min(120, default_k)}
    if where:
        search_kwargs["filter"] = where
    return vector_store.as_retriever(search_kwargs=search_kwargs)


@retrieval_node("chroma")
def chroma_node(state: PipelineState) -> NodeResult:
    retriever = get_retriever(state.team_nums, state.season)
    docs = retriever.invoke(state.question)
    if not docs:
        return NodeResult(source="chroma", status=STATUS_EMPTY)
    text = "\n\n".join(d.page_content for d in docs)
    return NodeResult(source="chroma", status=STATUS_OK, text=text)
