"""Fuses zero or more external NodeResults into one prompt-ready block.

Two responsibilities that must never be separated: rendering the block, and
neutralizing it as an *injection surface* (see docs/security.md). External
text is attacker-reachable -- a forum post or video caption can contain an
"ignore previous instructions" style payload -- so every source is
sanitized and fenced under an explicit "untrusted" header before it ever
reaches the LLM, and the system prompt (chain.EXTRA_RULES) tells the model
to treat it as opinion data, never as instructions.

`fuse()` returns `None` when nothing usable came back from any source, so
`chain.answer` can fall back to the unchanged pre-pipeline prompt path --
see tests/unit/test_prompt_compat.py.
"""
import re
from dataclasses import dataclass

import config
from nodes.base import STATUS_OK

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE_RE = re.compile(r"[ \t]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
# Delimiter-lookalikes an injection payload would use to try to escape the
# fenced block or masquerade as a system/human turn boundary.
_DELIMITER_RE = re.compile(
    r"(?im)^\s*(system|human|assistant|ai)\s*:|```|<\|.*?\|>|\[/?(?:system|context|instructions)\]"
)

SOURCE_LABELS = {
    "chief_delphi": "Chief Delphi",
    "reddit": "Reddit (r/FTC)",
    "youtube": "YouTube video transcript",
}


def _sanitize(text: str) -> str:
    text = _CONTROL_CHARS_RE.sub("", text)
    text = _DELIMITER_RE.sub("[filtered]", text)
    text = _WHITESPACE_RE.sub(" ", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text.rfind(" ", 0, max_chars)
    if cut <= 0:
        cut = max_chars
    return text[:cut].rstrip() + " [truncated]"


@dataclass(frozen=True)
class FusedContext:
    text: str
    citations: tuple = ()
    sources_used: tuple = ()


def fuse(external_results: dict) -> "FusedContext | None":
    """`external_results` is {source_name: NodeResult} -- normally the
    subset of `run_nodes`'s output that excludes the always-on `stats` and
    `chroma` nodes."""
    blocks = []
    citations = []
    sources_used = []
    remaining_total = config.MAX_EXTERNAL_CHARS_TOTAL

    # Deterministic order, not dict/thread-completion order, so output is
    # reproducible across runs of the same question.
    for name in sorted(external_results):
        result = external_results[name]
        if result.status != STATUS_OK or not result.text.strip():
            continue
        clean = _sanitize(result.text)
        if not clean:
            continue
        budget = min(config.MAX_EXTERNAL_CHARS_PER_SOURCE, remaining_total)
        if budget <= 0:
            break
        clean = _truncate(clean, budget)
        remaining_total -= len(clean)

        label = SOURCE_LABELS.get(name, name)
        blocks.append(f"[{label}]\n{clean}")
        citations.extend(result.citations)
        sources_used.append(name)

    if not blocks:
        return None

    return FusedContext(
        text="\n\n".join(blocks),
        citations=tuple(citations),
        sources_used=tuple(sources_used),
    )


def render_sources_footer(sources_used: tuple) -> str:
    if not sources_used:
        return ""
    labels = [SOURCE_LABELS.get(s, s) for s in sources_used]
    return f"\n\n_Sources consulted: {', '.join(labels)}_"
