"""Entity extraction: find FTC team numbers mentioned in a free-text question.

Two independent passes, merged:
  1. Numeric — bare team numbers (`14469`, `team 112`, `#9295`).
  2. Name — greedy longest-n-gram match against a team-name index built
     from the region's name->number map.

Both passes exist in the original implementation; this version fixes three
concrete false-positive/false-negative sources found by testing against the
real ~9,400-team US index:

  - The team named "HOW" (14469) matched almost every question, because
    ordinary question words ("How many...", "How did...") were never
    filtered. Single-token name matches now require the token be at least
    4 characters AND not a common English/FTC-domain word.
  - Numbers were only accepted if present in the (region-limited) index, so
    a team outside the queried region could never be matched by number at
    all. Numbers are now validated by shape (3-6 digits, not a bare
    season-year) instead of by index membership.
  - Space-separated and concatenated spelling variants of the same name
    ("Robo Knights" vs "RoboKnights") indexed under disjoint keys, so half
    of the real teams using either spelling were unreachable by the other.
    Multi-token names are now indexed under both their spaced and
    concatenated forms.
"""
import re

# Common English words that would otherwise match a real, unfortunately-named
# team ("HOW" -> 14469) on nearly every natural-language question.
_FUNCTION_WORD_STOPLIST = {
    "how", "what", "who", "why", "when", "where", "which",
    "the", "a", "an", "of", "is", "are", "does", "did", "do", "done",
    "was", "were", "will", "would", "should", "could", "can", "cant",
    "has", "have", "had", "this", "that", "these", "those", "there", "here",
    "very", "really", "just", "only", "also", "about", "above", "after",
    "again", "against", "all", "am", "any", "because", "before", "being",
    "below", "between", "both", "but", "by", "down", "during", "each",
    "few", "for", "from", "further", "if", "in", "into", "more", "most",
    "no", "nor", "not", "now", "off", "on", "once", "or", "other", "out",
    "over", "own", "same", "so", "some", "such", "than", "then", "through",
    "to", "too", "under", "until", "up", "with", "without",
    "me", "my", "we", "us", "our", "you", "your", "he", "him", "his",
    "she", "her", "it", "its", "they", "them", "their", "i",
}

# FTC scouting vocabulary that would otherwise trigger on a similarly-named team.
_DOMAIN_STOPLIST = {
    "match", "matches", "event", "events", "score", "scores", "point",
    "points", "auto", "teleop", "endgame", "opr", "rank", "ranks",
    "ranking", "rankings", "award", "awards", "season", "seasons",
    "region", "regions", "robot", "robots", "alliance", "alliances",
    "qual", "quals", "playoff", "playoffs", "worlds", "states", "league",
    "meet", "meets", "tournament", "tournaments", "championship",
    "championships", "win", "wins", "won", "loss", "losses", "lost",
    "tie", "ties", "record", "stats", "stat", "team", "teams", "vs",
    "versus", "beating", "beat", "chances",
}

STOP_WORDS = _FUNCTION_WORD_STOPLIST | _DOMAIN_STOPLIST

_MIN_SINGLE_TOKEN_LEN = 4
_MAX_TEAMS_RETURNED = 6

_PREFIXED_NUMBER_RE = re.compile(r"(?:team|#)\s*#?\s*(\d{1,6})\b", re.IGNORECASE)
_BARE_NUMBER_RE = re.compile(r"\b\d{1,6}\b")
_WORD_RE = re.compile(r"\b[a-z0-9]+\b")
_ORIG_WORD_RE = re.compile(r"\b[A-Za-z0-9]+\b")
_PUNCT_RE = re.compile(r"['\-\._]")
# Strip a possessive "'s" suffix on the QUESTION side before the general
# punctuation strip runs, so "HOW's chances" tokenizes as "how" + "chances"
# rather than fusing into one unmatchable "hows" token. Not applied to team
# names themselves -- possessives are a feature of how people phrase
# questions, not of how teams are named.
_POSSESSIVE_RE = re.compile(r"(?<=[A-Za-z0-9])'s\b")

# Words immediately preceding a name that signal "this is a team reference",
# even if the name itself is a short/stoplisted word.
_TEAM_PRECEDING_WORDS = {"team", "teams", "named"}


def _is_bare_team_number(token: str) -> bool:
    """3-6 digit numbers are accepted unprefixed. 1-2 digits are too ambiguous
    ('top 5 teams') without a 'team'/'#' prefix. Bare 4-digit numbers that look
    like a season year (2000-2099) are assumed to be a year, not a team number,
    unless prefixed."""
    if len(token) <= 2:
        return False
    if len(token) == 4 and token.startswith("20"):
        return False
    return True


def _normalize(name: str) -> list[str]:
    clean = _PUNCT_RE.sub("", name.lower())
    return _WORD_RE.findall(clean)


def build_name_index(region_teams_dict: dict) -> dict[str, set[int]]:
    """Map normalized team-name text -> set of team numbers.

    Multi-token names are indexed under both their space-joined form
    ("robo knights") and their concatenated form ("roboknights"), so a
    punctuation/spacing variant of a multi-word name still resolves. This is
    a one-way widening: a single-token name has no reliable way to be split
    back into words, so it is indexed only under its natural form.
    """
    index: dict[str, set[int]] = {}
    for raw_name, number in region_teams_dict.items():
        words = _normalize(raw_name)
        if not words:
            continue
        keys = {" ".join(words)}
        if len(words) > 1:
            keys.add("".join(words))
        for key in keys:
            index.setdefault(key, set()).add(int(number))
    return index


def _has_team_context_signal(orig_words: list[str], q_words: list[str], i: int, whole_q_upper: bool) -> bool:
    """Strong signals that a short/stoplisted single-token match at position
    `i` is genuinely a team reference: the user wrote it ALL-CAPS (and
    wasn't just shouting the whole question), or explicitly prefixed it with
    "team"/"teams"/"named". This is what lets "team HOW" or "HOW" (the team
    named 14469) still resolve, while "How many matches..." (ordinary
    sentence case) still doesn't."""
    orig_tok = orig_words[i]
    is_allcaps = len(orig_tok) >= 2 and orig_tok.isupper() and not whole_q_upper
    preceded_by_team_word = i > 0 and q_words[i - 1] in _TEAM_PRECEDING_WORDS
    return is_allcaps or preceded_by_team_word


def extract_info(question: str, region_teams_dict: dict) -> list[tuple[int, str, str]]:
    """Find team numbers mentioned in `question`.

    Returns a list of `(team_num, matched_span, source)` tuples sorted by
    team number, deduplicated, capped at 6. `source` is `"number"` or
    `"name"` — useful for echoing back what was matched ("I read that as
    Team 9295 (Robo Knights)") so a bad match is visible instead of silent.
    """
    region_teams_dict = region_teams_dict or {}
    found: dict[int, tuple[str, str]] = {}

    for m in _PREFIXED_NUMBER_RE.finditer(question):
        found[int(m.group(1))] = (m.group(0), "number")

    for m in _BARE_NUMBER_RE.finditer(question):
        token = m.group(0)
        if _is_bare_team_number(token):
            found.setdefault(int(token), (token, "number"))

    name_index = build_name_index(region_teams_dict)
    if name_index:
        punct_stripped = _PUNCT_RE.sub("", _POSSESSIVE_RE.sub("", question))
        q_words = _WORD_RE.findall(punct_stripped.lower())
        # Case-preserving tokenization of the same stripped text, so token
        # counts stay aligned with q_words -- orig_words[i] is q_words[i]
        # before lowercasing.
        orig_words = _ORIG_WORD_RE.findall(punct_stripped)
        whole_q_upper = question.isupper()
        max_ngram = min(5, max((len(k.split()) for k in name_index), default=1))

        used_indices: set[int] = set()
        for n in range(max_ngram, 0, -1):
            for i in range(len(q_words) - n + 1):
                if any(idx in used_indices for idx in range(i, i + n)):
                    continue
                ngram = " ".join(q_words[i:i + n])
                if n == 1 and (len(ngram) < _MIN_SINGLE_TOKEN_LEN or ngram in STOP_WORDS):
                    if not _has_team_context_signal(orig_words, q_words, i, whole_q_upper):
                        continue
                if ngram in name_index:
                    for team_num in name_index[ngram]:
                        found.setdefault(team_num, (ngram, "name"))
                    used_indices.update(range(i, i + n))

    ordered = sorted(found.items())[:_MAX_TEAMS_RETURNED]
    return [(num, span, source) for num, (span, source) in ordered]


def extract_team_numbers(question: str, region_teams_dict: dict) -> list[int]:
    """Convenience wrapper returning just the team numbers, for callers that
    don't need match provenance."""
    return [num for num, _span, _source in extract_info(question, region_teams_dict)]
