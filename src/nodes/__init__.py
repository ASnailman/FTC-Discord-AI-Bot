"""External node registry: source name -> @retrieval_node-wrapped callable.

`stats`/`chroma` are always active and referenced directly by chain.py; this
registry holds only the *optional* external sources, so chain.py and
nodes.router can name a source once (e.g. "chief_delphi") without every
caller needing its own import of every node module. Populated as each
external node is added; an empty registry means the pipeline always falls
back to rag_chain.ask_bot unchanged (see chain.py).
"""
from nodes.chief_delphi_node import chief_delphi_node
from nodes.reddit_node import reddit_node
from nodes.youtube_node import youtube_node

EXTERNAL_NODES = {
    "chief_delphi": chief_delphi_node,
    "reddit": reddit_node,
    "youtube": youtube_node,
}
