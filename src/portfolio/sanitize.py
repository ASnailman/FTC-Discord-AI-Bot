"""Prompt-injection neutralization for portfolio inputs.

Mirrors `nodes.fusion._sanitize`'s approach (same delimiter-lookalike
patterns) for this feature's two attacker-reachable text surfaces:
uploaded file content and the user's free-text customization
`instructions`. Both are fenced under an explicit untrusted header before
ever reaching the LLM -- see compose.py -- and the system prompt tells the
model this text is data, never direction.
"""
import re

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE_RE = re.compile(r"[ \t]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
# Delimiter-lookalikes an injection payload would use to try to escape the
# fenced block or masquerade as a system/human turn boundary.
_DELIMITER_RE = re.compile(
    r"(?im)^\s*(system|human|assistant|ai)\s*:|```|<\|.*?\|>|\[/?(?:system|context|instructions)\]"
)


def sanitize(text: str) -> str:
    text = _CONTROL_CHARS_RE.sub("", text or "")
    text = _DELIMITER_RE.sub("[filtered]", text)
    text = _WHITESPACE_RE.sub(" ", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text.rfind(" ", 0, max_chars)
    if cut <= 0:
        cut = max_chars
    return text[:cut].rstrip() + " [truncated]"
