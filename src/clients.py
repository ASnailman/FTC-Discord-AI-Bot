"""Process-wide singletons for the heavy clients.

`rag_chain.ask_bot` used to construct the embedding model, LLM, and Chroma
client from scratch on every `/ask` call — reloading a sentence-transformer
model off disk each time. These factories build each client once per
process and cache it.
"""
from functools import lru_cache

import chromadb
from langchain_chroma import Chroma
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_huggingface import HuggingFaceEmbeddings

import config


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(model_name=config.EMBEDDING_MODEL)


@lru_cache(maxsize=1)
def get_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=config.GEMINI_MODEL,
        temperature=config.GEMINI_TEMPERATURE,
        max_tokens=config.GEMINI_MAX_TOKENS,
    )


@lru_cache(maxsize=1)
def get_llm_with_context() -> ChatGoogleGenerativeAI:
    """Same model, larger max_tokens -- used only by `chain.answer` when
    external context is actually fused into the prompt, so the
    no-external-sources path (the vast majority of questions) keeps today's
    exact token budget and truncation behavior unchanged."""
    return ChatGoogleGenerativeAI(
        model=config.GEMINI_MODEL,
        temperature=config.GEMINI_TEMPERATURE,
        max_tokens=config.GEMINI_MAX_TOKENS_WITH_CONTEXT,
    )


@lru_cache(maxsize=1)
def get_chroma_client():
    config.CHROMA_PATH.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(config.CHROMA_PATH))


@lru_cache(maxsize=1)
def get_vector_store() -> Chroma:
    return Chroma(
        client=get_chroma_client(),
        collection_name=config.CHROMA_COLLECTION,
        embedding_function=get_embeddings(),
    )


def warm_up():
    """Force-load every singleton. Call once at startup so the first /ask
    isn't the one paying for the model load."""
    get_embeddings()
    get_llm()
    get_vector_store()
