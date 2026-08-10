"""A deterministic, dependency-free embedding function for tests.

The real pipeline uses `all-MiniLM-L6-v2` (a ~90 MB sentence-transformer, plus
torch). Downloading and running it in every test would make the offline tier
slow and non-hermetic — and it's unnecessary, because the bugs this test
suite targets (missing metadata filters, colliding chunk IDs) are
embedding-independent: with a correct `where` filter applied, retrieval
precision is 1.0 regardless of which vectors are used.

This hashes whitespace tokens into a small fixed-size bag-of-words vector and
L2-normalizes it, so semantically similar short strings land close together
under cosine distance without ever loading a model. It implements both
protocols used in this codebase:
  - chromadb's `EmbeddingFunction` (`__call__`), used by `VectorDBManager`.
  - langchain_core's `Embeddings` (`embed_documents`/`embed_query`), used by
    `langchain_chroma.Chroma` in `rag_chain.py`.
"""
import hashlib
import math
import re

from langchain_core.embeddings import Embeddings

_DIM = 64
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _hash_vector(text: str) -> list[float]:
    vec = [0.0] * _DIM
    for token in _TOKEN_RE.findall(text.lower()):
        idx = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % _DIM
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class DeterministicHashEmbeddingFunction(Embeddings):
    """Usable as both a chromadb EmbeddingFunction and a langchain Embeddings."""

    def name(self) -> str:  # chromadb EmbeddingFunction convention
        return "deterministic-hash-64"

    def __call__(self, input):  # chromadb protocol: input is a list[str]
        return [_hash_vector(t) for t in input]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [_hash_vector(t) for t in texts]

    def embed_query(self, input):  # noqa: A002 (name matches chromadb's protocol)
        # langchain's Embeddings.embed_query passes a single string and wants
        # a single vector back; chromadb's EmbeddingFunction.embed_query
        # passes a list (even for one query) and wants a list of vectors.
        # Support both call conventions since this shim backs both callers.
        if isinstance(input, str):
            return _hash_vector(input)
        return [_hash_vector(t) for t in input]
